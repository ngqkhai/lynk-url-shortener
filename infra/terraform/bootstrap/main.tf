provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = ["231136241975"]
}

variable "state_bucket_name" {
  description = "Dedicated state bucket; verify availability and ownership before creation."
  type        = string

  validation {
    condition     = can(regex("^lynk-tfstate-231136241975-ap-southeast-1-[a-z0-9-]+$", var.state_bucket_name))
    error_message = "Use the dedicated Lynk state bucket prefix and a verified unique suffix."
  }
}

resource "aws_s3_bucket" "state" {
  bucket        = var.state_bucket_name
  force_destroy = false

  tags = {
    Project = "lynk"
    Purpose = "terraform-state"
    Owner   = "terraform-bootstrap"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Resource policy only denies insecure transport. IAM still governs who may read
# or change state; application and legacy delivery roles receive no new access.
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.state.arn,
        "${aws_s3_bucket.state.arn}/*"
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.id
}
