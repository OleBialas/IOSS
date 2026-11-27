output "launcher_url" {
  description = "Give this URL and the access code to the learners"
  value       = aws_lambda_function_url.launcher.function_url
}

output "sessions_table" {
  value = aws_dynamodb_table.sessions.name
}
