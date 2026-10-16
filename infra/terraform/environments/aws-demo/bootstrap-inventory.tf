# Bootstrap only reads the environment output contract. It cannot write state.
resource "aws_iam_role_policy" "bootstrap_inventory" {
  name = "terraform-inventory-read"
  role = aws_iam_role.bootstrap.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "s3:GetObject"
      Resource = "arn:aws:s3:::lynk-tfstate-231136241975-ap-southeast-1-aws-demo/environments/aws-demo/terraform.tfstate"
      }, {
      Effect   = "Allow"
      Action   = "s3:ListBucket"
      Resource = "arn:aws:s3:::lynk-tfstate-231136241975-ap-southeast-1-aws-demo"
      Condition = {
        StringLike = {
          "s3:prefix" = ["env:/", "environments/aws-demo/", "environments/aws-demo/terraform.tfstate"]
        }
      }
    }]
  })
}
