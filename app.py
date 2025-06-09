from flask import Flask, request, jsonify
import boto3
from datetime import datetime, timezone, timedelta
import os

app = Flask(__name__)

@app.route("/", methods=["POST"])
def check_object():
    # Set AWS credentials from environment variables
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    if not aws_access_key or not aws_secret_key:
        return jsonify({"error": "Missing AWS credentials in environment variables"}), 500

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )

    try:
        body = request.get_json(force=True, silent=True)
        if not body:
            return jsonify({"error": "No JSON body provided"}), 400
    except Exception:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    bucket = body.get("bucket")
    filename = body.get("filename")
    max_age_hours = body.get("max_age_hours")

    if not all([bucket, filename, max_age_hours]):
        return jsonify({"error": "Missing bucket, filename, or max_age_hours"}), 400

    try:
        max_age_hours = float(max_age_hours)
    except ValueError:
        return jsonify({"error": "max_age_hours must be a number"}), 400

    try:
        head = s3.head_object(Bucket=bucket, Key=filename)
        last_modified = head["LastModified"]
        age = datetime.now(timezone.utc) - last_modified

        if age < timedelta(hours=max_age_hours):
            return jsonify({"status": "OK", "age": str(age)}), 200
        else:
            return jsonify({"status": "Too old", "age": str(age)}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
