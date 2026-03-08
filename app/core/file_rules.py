FILE_RULES = {
    "payment_slip": {
        "folder_id": "1UVk4ND0xOWlmxQ1DkpcSxsjd8dLp0kkl",
        "roles": ["sale", "manager"]
    },
    # Sale on CreateOrderPage: picture of address / request (lazy to type). Folder: sale request invoice.
    "invoice": {
        "folder_id": "1PLQxBdFAvSzQT16s75jEOUvhF1ox_J41",
        "roles": ["sale", "account", "manager"]
    },
    # Account/manager on Invoice Submit page: complete invoice file to return to customer. Separate folder.
    "invoice_submit": {
        "folder_id": "1My_qpPyw9HnvVCmofFqCMYMWxUiDTFMC",
        "roles": ["account", "manager"]
    },
    "return_evidence": {
        "folder_id": "1GVrzVsxhd46TKx1f9czHf5AbYr_JQi0z",
        "roles": ["pack", "manager"]
    },

    "shipping_address_image": {
        "folder_id": "1xylCx5HYgmqYghMbt2FWayeoxXXHTXf0",
        "roles": ["sale", "manager"]
    },

    "chat_evidence": {
        "folder_id": "1sSXaoe2jnPsD0uY7OBDyxug14nSpgjiA",
        "roles": ["sale", "manager"]
    }
}
