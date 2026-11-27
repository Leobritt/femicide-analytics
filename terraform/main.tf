# Camada de dados: um PostgreSQL em container, com volume persistente.
# As tabelas e visões são criadas pelo ETL (python -m etl.run_etl), não aqui.

resource "docker_image" "postgres" {
  name         = "postgres:${var.postgres_version}"
  keep_locally = true
}

resource "docker_volume" "dados" {
  name = "${var.container_name}-data"
}

resource "docker_container" "postgres" {
  name    = var.container_name
  image   = docker_image.postgres.image_id
  restart = "unless-stopped"

  env = [
    "POSTGRES_DB=${var.db_name}",
    "POSTGRES_USER=${var.db_user}",
    "POSTGRES_PASSWORD=${var.db_password}",
  ]

  ports {
    internal = 5432
    external = var.host_port
    ip       = var.bind_address
  }

  volumes {
    volume_name    = docker_volume.dados.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U ${var.db_user} -d ${var.db_name}"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }

  # só devolve o controle quando o banco já aceita conexões
  wait         = true
  wait_timeout = 90
}
