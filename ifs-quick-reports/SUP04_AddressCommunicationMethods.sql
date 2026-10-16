SELECT *
FROM   COMM_METHOD
WHERE  identity IN (SELECT supplier_id FROM SUPPLIER_INFO_GENERAL) AND address_id IS NOT NULL
ORDER  BY identity, address_id
