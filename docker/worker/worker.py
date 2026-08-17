import os
import boto3
from flask import Flask, request, jsonify

app = Flask(__name__)

s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])
sns = boto3.client("sns", region_name=os.environ["AWS_REGION"])

BUCKET = os.environ["S3_BUCKET"]
TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")  # optional until SNS is set up

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    file = request.files["file"]
    key = file.filename
    s3.upload_fileobj(file, BUCKET, key)

    if TOPIC_ARN:
        sns.publish(
            TopicArn=TOPIC_ARN,
            Subject="New file uploaded",
            Message=f"File '{key}' was uploaded to bucket '{BUCKET}'.",
        )

    return jsonify({"status": "uploaded", "key": key}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)