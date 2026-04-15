# 📸 AWS Lambda Photo Compressor

An event-driven, serverless image compression system built using **AWS Lambda, S3, SNS, and Pillow**.

When a photo is uploaded to an S3 bucket, the Lambda function:
1. Fetches the image
2. Compresses and resizes it
3. Uploads it to another S3 bucket
4. Sends a notification via SNS

---

## 🏗 Architecture

S3 (Raw Photos)
        ↓
Lambda (Pillow Compression)
        ↓
S3 (Compressed Photos)
        ↓
SNS Notification (Email / HTTP)

---

## 🚀 Features

- Automatic image compression on upload
- JPEG quality & resize control via environment variables
- PNG transparency preserved
- EXIF metadata removed (privacy + size reduction)
- Progressive JPEG optimization
- SNS notification with compression stats
- Fully serverless & cost-efficient

---

## 🛠 Tech Stack

- AWS Lambda (Python 3.12)
- Amazon S3
- Amazon SNS
- Pillow (via Lambda Layer)
- IAM (least-privilege policy)

---

## 📦 Project Structure

<img width="995" height="396" alt="Screenshot 2026-04-15 200032" src="https://github.com/user-attachments/assets/f0aa3123-e77c-4f21-9607-14622430ad59" />


---

## ⚙️ Setup Instructions

### 1️⃣ Create S3 Buckets
- `my-raw-photos`
- `my-compressed-photos`

Enable **PutObject event notification** on `my-raw-photos`.

---

### 2️⃣ Create SNS Topic
- Name: `photo-compress-topic`
- Add Email / HTTP subscription
- Confirm subscription

---

### 3️⃣ Create Lambda Layer (Pillow)

Use **Klayers** ARN (region-specific):

Example (us-east-1): arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p312-Pillow:1


---

### 4️⃣ Create Lambda Function

- Runtime: Python 3.12
- Handler: `lambda_function.lambda_handler`
- Memory: 512 MB
- Timeout: 30 seconds

Attach:
- Pillow Lambda Layer
- IAM role using provided policy

---

### 5️⃣ Environment Variables

| Key | Value |
|----|------|
| RAW_BUCKET | my-raw-photos |
| COMPRESSED_BUCKET | my-compressed-photos |
| SNS_TOPIC_ARN | your-sns-arn |
| JPEG_QUALITY | 60 |
| MAX_WIDTH | 1920 |
| MAX_HEIGHT | 1080 |

---

## 🧪 Testing

1. Upload image to `my-raw-photos`
2. Lambda triggers automatically
3. Compressed image appears in output bucket
4. SNS notification received

---

## 📊 Sample SNS Output

```json
{
  "status": "SUCCESS",
  "original_file": "uploads/photo.jpg",
  "compressed_file": "uploads/photo_compressed.jpg",
  "original_size_kb": 2450.5,
  "compressed_size_kb": 620.3,
  "savings_percent": 74.7
}


👨‍💻 Author

Anand Mahangade
Cloud & DevOps Engineer
AWS | Docker | Linux | Automation
