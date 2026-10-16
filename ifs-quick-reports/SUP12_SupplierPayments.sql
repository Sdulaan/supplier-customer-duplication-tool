SELECT *
FROM   IDENTITY_PAY_INFO_CFV
WHERE  party_type_db = 'SUPPLIER'
ORDER  BY identity, company
