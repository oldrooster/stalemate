from flask import Flask, request, jsonify, g
import boto3
from datetime import datetime, timezone, timedelta
import logging
import os
import sys
import uuid

app = Flask(__name__)


def configure_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )
    app.logger.setLevel(log_level)
    app.logger.info("Logging initialized", extra={"log_level": log_level})


configure_logging()


@app.before_request
def log_request_start():
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.request_started_at = datetime.now(timezone.utc)
    app.logger.info(
        "Request started: request_id=%s method=%s path=%s remote_addr=%s",
        g.request_id,
        request.method,
        request.path,
        request.remote_addr,
    )


@app.after_request
def log_request_end(response):
    request_id = getattr(g, "request_id", "unknown")
    started_at = getattr(g, "request_started_at", None)
    duration_ms = (
        int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
        if started_at
        else -1
    )
    app.logger.info(
        "Request completed: request_id=%s status=%s duration_ms=%s",
        request_id,
        response.status_code,
        duration_ms,
    )
    return response

@app.route("/", methods=["POST"])
def check_object():
    request_id = getattr(g, "request_id", "unknown")

    try:
        body = request.get_json(force=True, silent=True)
        if not body:
            app.logger.warning("No JSON body provided: request_id=%s", request_id)
            return jsonify({"error": "No JSON body provided"}), 400
    except Exception:
        app.logger.exception("Failed to parse JSON body: request_id=%s", request_id)
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    app.logger.info(
        "Parsed request JSON: request_id=%s keys=%s",
        request_id,
        sorted(list(body.keys())),
    )

    # AWS credentials: use request body if provided, fall back to environment variables
    aws_access_key = body.get("aws_access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = body.get("aws_secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = body.get("aws_region") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    creds_source = "request" if body.get("aws_access_key_id") else "environment"

    if not aws_access_key or not aws_secret_key:
        app.logger.error(
            "Missing AWS credentials: request_id=%s — provide in request body or environment variables",
            request_id,
        )
        return jsonify({"error": "Missing AWS credentials — provide in request body or environment variables"}), 400

    app.logger.info(
        "AWS configuration loaded: request_id=%s region=%s credentials_source=%s",
        request_id,
        aws_region,
        creds_source,
    )

    if os.environ.get("UNSAFE_SHOW_CREDS", "").lower() in ("1", "true", "yes"):
        app.logger.warning(
            "UNSAFE_SHOW_CREDS enabled — request_id=%s access_key=%s secret_key=%s region=%s",
            request_id, aws_access_key, aws_secret_key, aws_region,
        )

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )

    bucket = body.get("bucket")
    filename = body.get("filename")
    max_age_hours = body.get("max_age_hours")

    if not all([bucket, filename, max_age_hours]):
        app.logger.warning(
            "Missing required payload values: request_id=%s bucket_present=%s filename_present=%s max_age_hours_present=%s",
            request_id,
            bool(bucket),
            bool(filename),
            bool(max_age_hours),
        )
        return jsonify({"error": "Missing bucket, filename, or max_age_hours"}), 400

    app.logger.info(
        "Validating object age request: request_id=%s bucket=%s filename=%s max_age_hours=%s",
        request_id,
        bucket,
        filename,
        max_age_hours,
    )

    try:
        max_age_hours = float(max_age_hours)
    except ValueError:
        app.logger.warning(
            "max_age_hours is not numeric: request_id=%s value=%s",
            request_id,
            max_age_hours,
        )
        return jsonify({"error": "max_age_hours must be a number"}), 400

    try:
        app.logger.info(
            "Checking S3 object metadata: request_id=%s bucket=%s key=%s",
            request_id,
            bucket,
            filename,
        )
        head = s3.head_object(Bucket=bucket, Key=filename)
        last_modified = head["LastModified"]
        age = datetime.now(timezone.utc) - last_modified

        app.logger.info(
            "Computed object age: request_id=%s bucket=%s key=%s last_modified=%s age=%s threshold_hours=%s",
            request_id,
            bucket,
            filename,
            last_modified,
            age,
            max_age_hours,
        )

        if age < timedelta(hours=max_age_hours):
            app.logger.info("Object is within acceptable age: request_id=%s", request_id)
            return jsonify({"status": "OK", "age": str(age)}), 200
        else:
            app.logger.warning("Object is too old: request_id=%s", request_id)
            return jsonify({"status": "Too old", "age": str(age)}), 500

    except s3.exceptions.ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "403":
            app.logger.error(
                "Access denied to S3 object: request_id=%s bucket=%s key=%s — check IAM permissions and credentials",
                request_id, bucket, filename,
            )
            return jsonify({"error": "Access denied — check AWS credentials and IAM permissions"}), 500
        elif error_code == "404":
            app.logger.error(
                "S3 object not found: request_id=%s bucket=%s key=%s",
                request_id, bucket, filename,
            )
            return jsonify({"error": f"Object not found: s3://{bucket}/{filename}"}), 404
        else:
            app.logger.error(
                "S3 error (%s): request_id=%s bucket=%s key=%s — %s",
                error_code, request_id, bucket, filename, e,
            )
            return jsonify({"error": f"S3 error ({error_code})"}), 500
    except Exception as e:
        app.logger.error(
            "Unexpected error: request_id=%s bucket=%s key=%s — %s",
            request_id, bucket, filename, e,
        )
        return jsonify({"error": str(e)}), 500
