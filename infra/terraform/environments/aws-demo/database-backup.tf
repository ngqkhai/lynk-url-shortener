# CP11: independent, private logical-backup storage for the service-owned Neon databases.
resource "aws_s3_bucket" "database_backups" {
  bucket              = "lynk-db-backups-231136241975-ap-southeast-1"
  bucket_namespace    = "global"
  force_destroy       = false
  object_lock_enabled = false
  region              = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
    Purpose     = "database-backups"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "database_backups" {
  bucket                  = aws_s3_bucket.database_backups.id
  region                  = "ap-southeast-1"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "database_backups" {
  bucket = aws_s3_bucket.database_backups.id
  region = "ap-southeast-1"
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "database_backups" {
  bucket = aws_s3_bucket.database_backups.id
  region = "ap-southeast-1"
  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "database_backups_tls" {
  bucket = aws_s3_bucket.database_backups.id
  region = "ap-southeast-1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.database_backups.arn,
        "${aws_s3_bucket.database_backups.arn}/*"
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_iam_role_policy" "node_database_backups" {
  name = "lynk-database-backups"
  role = aws_iam_role.node.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:GetBucketLocation"
        Resource = aws_s3_bucket.database_backups.arn
      },
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.database_backups.arn
        Condition = {
          StringLike = { "s3:prefix" = ["db-backups/*"] }
        }
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [
          "${aws_s3_bucket.database_backups.arn}/db-backups/lynk_urls/*",
          "${aws_s3_bucket.database_backups.arn}/db-backups/lynk_redirects/*",
          "${aws_s3_bucket.database_backups.arn}/db-backups/lynk_auth/*"
        ]
      }
    ]
  })
}
