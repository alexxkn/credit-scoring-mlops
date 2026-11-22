terraform {
  required_providers {
    vkcs = { source = "vk-cs/vkcs" }
  }
}

data "vkcs_networking_network" "external" {
  name = var.external_network_name
}

resource "vkcs_networking_network" "this" {
  name = "${var.name}-net"
  sdn  = "sprut"
}

resource "vkcs_networking_subnet" "nodes" {
  name            = "${var.name}-nodes"
  network_id      = vkcs_networking_network.this.id
  cidr            = var.nodes_cidr
  dns_nameservers = var.dns_nameservers
  sdn             = "sprut"
}

resource "vkcs_networking_router" "this" {
  name                = "${var.name}-router"
  external_network_id = data.vkcs_networking_network.external.id
  sdn                 = "sprut"
}

resource "vkcs_networking_router_interface" "nodes" {
  router_id = vkcs_networking_router.this.id
  subnet_id = vkcs_networking_subnet.nodes.id
  sdn       = "sprut"
}
