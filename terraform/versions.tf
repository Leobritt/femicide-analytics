terraform {
  required_version = ">= 1.5"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

# O mesmo código provisiona o banco na máquina local (padrão) ou na VM da equipe:
# basta apontar docker_host para "ssh://usuario@servidor" (ver variables.tf).
provider "docker" {
  host = var.docker_host
}
