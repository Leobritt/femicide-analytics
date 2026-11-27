output "container_name" {
  description = "Container do banco."
  value       = docker_container.postgres.name
}

output "endpoint" {
  description = "Endereço e porta em que o banco responde."
  value       = "${var.bind_address}:${var.host_port}"
}

output "database_url" {
  description = "URL para o .env (DATABASE_URL). Marcada como sensível: terraform output -raw database_url."
  value       = "postgres://${var.db_user}:${var.db_password}@${var.bind_address}:${var.host_port}/${var.db_name}?sslmode=disable"
  sensitive   = true
}
