output "network_id" {
  value = vkcs_networking_network.this.id
}

output "subnet_id" {
  value = vkcs_networking_subnet.nodes.id
}

output "subnet_cidr" {
  value = vkcs_networking_subnet.nodes.cidr
}

output "external_network_id" {
  value = data.vkcs_networking_network.external.id
}

output "router_interface_id" {
  value = vkcs_networking_router_interface.nodes.id
}
