data "archive_file" "launcher" {
  type        = "zip"
  output_path = "${path.module}/build/launcher.zip"

  dynamic "source" {
    for_each = fileset("${path.module}/../launcher/src", "*.{py,html,sh}")
    content {
      content  = file("${path.module}/../launcher/src/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_cloudwatch_log_group" "launcher" {
  name              = "/aws/lambda/${var.name_prefix}-launcher"
  retention_in_days = 14
}

resource "aws_lambda_function" "launcher" {
  function_name    = "${var.name_prefix}-launcher"
  role             = aws_iam_role.launcher.arn
  runtime          = "python3.13"
  handler          = "app.handler"
  filename         = data.archive_file.launcher.output_path
  source_code_hash = data.archive_file.launcher.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      ACCESS_CODE        = var.access_code
      MAX_SESSIONS       = tostring(var.max_sessions)
      SESSION_MINUTES    = tostring(var.session_minutes)
      NAME_PREFIX        = var.name_prefix
      TABLE_NAME         = aws_dynamodb_table.sessions.name
      LAUNCH_TEMPLATE_ID = aws_launch_template.sandbox.id
      BUNDLE_BUCKET      = aws_s3_bucket.bundle.id
      BUNDLE_KEY         = aws_s3_object.bundle.key
      SEED_ISSUES        = tostring(local.seed_issues)
      REPO_PATH          = "tinystats/tinystats"
    }
  }

  depends_on = [aws_cloudwatch_log_group.launcher]
}

# Public: the page and the API check the access code themselves.
resource "aws_lambda_function_url" "launcher" {
  function_name      = aws_lambda_function.launcher.function_name
  authorization_type = "NONE"
}

# --- Reaper ---------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "reaper" {
  name                = "${var.name_prefix}-reaper"
  description         = "Terminate IOSS sandboxes after their lifetime"
  schedule_expression = "rate(10 minutes)"
}

resource "aws_cloudwatch_event_target" "reaper" {
  rule  = aws_cloudwatch_event_rule.reaper.name
  arn   = aws_lambda_function.launcher.arn
  input = jsonencode({ action = "reap" })
}

resource "aws_lambda_permission" "reaper" {
  statement_id  = "AllowReaperSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.launcher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reaper.arn
}

# --- IAM ------------------------------------------------------------------

resource "aws_iam_role" "launcher" {
  name = "${var.name_prefix}-launcher"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "launcher_logs" {
  role       = aws_iam_role.launcher.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "launcher" {
  name = "launcher"
  role = aws_iam_role.launcher.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LaunchFromTemplateOnly"
        Effect = "Allow"
        Action = "ec2:RunInstances"
        Resource = [
          "${local.ec2_arn}:launch-template/${aws_launch_template.sandbox.id}",
          "${local.ec2_arn}:subnet/${aws_subnet.public.id}",
          "${local.ec2_arn}:security-group/${aws_security_group.sandbox.id}",
          "${local.ec2_arn}:instance/*",
          "${local.ec2_arn}:volume/*",
          "${local.ec2_arn}:network-interface/*",
          "arn:aws:ec2:${var.region}::image/*",
        ]
      },
      {
        Sid      = "TagOnLaunch"
        Effect   = "Allow"
        Action   = "ec2:CreateTags"
        Resource = ["${local.ec2_arn}:instance/*", "${local.ec2_arn}:volume/*"]
        Condition = {
          StringEquals = { "ec2:CreateAction" = "RunInstances" }
        }
      },
      {
        Sid      = "TerminateSandboxesOnly"
        Effect   = "Allow"
        Action   = "ec2:TerminateInstances"
        Resource = "${local.ec2_arn}:instance/*"
        Condition = {
          StringEquals = { "ec2:ResourceTag/ioss:managed" = "true" }
        }
      },
      {
        Sid      = "Describe"
        Effect   = "Allow"
        Action   = "ec2:DescribeInstances"
        Resource = "*"
      },
      {
        Sid      = "Sessions"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.sessions.arn
      },
      {
        # The launcher signs download URLs for the instances, so the
        # instances need no IAM role.
        Sid      = "Bundle"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.bundle.arn}/*"
      },
    ]
  })
}
