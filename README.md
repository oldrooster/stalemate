# stalemate

Stalemate is a simple Flask-based web service that checks the age of an object in an S3 bucket and returns HTTP 200 if the object is young enough, or HTTP 500 if it is too old.

## Features
- Checks the age of a specified S3 object
- Returns status based on a configurable age threshold
- Designed to run as a Docker container
- Uses Python 3.13

## Requirements
- Python 3.13+
- AWS credentials with permission to access the S3 bucket/object

## Usage

### 1. Build the Docker Image
```bash
docker build -t stalemate .
```

### 2. Run the Container
Replace the environment variable values with your AWS credentials and region:
```bash
docker run -e AWS_ACCESS_KEY_ID=your_access_key \
           -e AWS_SECRET_ACCESS_KEY=your_secret_key \
           -e AWS_DEFAULT_REGION=us-east-1 \
           -p 5000:5000 \
           stalemate
```

### 3. Make a Request
Send a POST request to the service:
```bash
curl -X POST http://localhost:5000/ \
     -H 'Content-Type: application/json' \
     -d '{"bucket": "your-bucket", "filename": "your-object-key", "max_age_hours": 24}'
```

- **bucket**: Name of the S3 bucket
- **filename**: Key of the S3 object
- **max_age_hours**: Maximum allowed age in hours

#### Example Response
- If the object is young enough:
  ```json
  {"status": "OK", "age": "0:10:00"}
  ```
- If the object is too old:
  ```json
  {"status": "Too old", "age": "2:00:00"}
  ```
- If there is an error:
  ```json
  {"error": "Missing bucket, filename, or max_age_hours"}
  ```

### 4. Deploy with Docker Compose
You can also deploy using Docker Compose. Create a `docker-compose.yml` file like this:

```yaml
version: '3.8'
services:
  stalemate:
    image: oldrooster/stalemate:latest
    ports:
      - "5000:5000"
    environment:
      AWS_ACCESS_KEY_ID: your_access_key
      AWS_SECRET_ACCESS_KEY: your_secret_key
      AWS_DEFAULT_REGION: us-east-1
```

Start the service with:
```bash
docker compose up
```

## Development
- `app.py`: Main Flask application
- `requirements.txt`: Python dependencies
- `Dockerfile`: Container build instructions

## License
MIT
