# Политики, которые VK Cloud создал вместе с кластером: Terraform берёт их под управление, а не создаёт дубли
import {
  to = module.kubernetes.vkcs_kubernetes_security_policy_v2.host_filesystem
  id = "3MTMIVLzjcqRabeUacWVBfKKxXP"
}

import {
  to = module.kubernetes.vkcs_kubernetes_security_policy_v2.host_namespace
  id = "3MTMIZm9YgXEgqiRg3QYu3WWKNI"
}
