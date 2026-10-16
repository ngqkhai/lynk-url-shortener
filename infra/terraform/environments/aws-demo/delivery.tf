# Preserve exact live document bytes: whitespace changes create a new version.
resource "aws_ssm_document" "deploy" {
  content         = file("${path.module}/deploy-document.json")
  document_format = "JSON"
  document_type   = "Command"
  name            = "LynkDeploy"
  permissions     = {}
  region          = "ap-southeast-1"
  tags            = {}
}

resource "aws_ssm_document" "argocd_status" {
  content         = file("${path.module}/argocd-status-document.json")
  document_format = "JSON"
  document_type   = "Command"
  name            = "LynkArgoStatus"
  permissions     = {}
  region          = "ap-southeast-1"
  tags            = {}
}
