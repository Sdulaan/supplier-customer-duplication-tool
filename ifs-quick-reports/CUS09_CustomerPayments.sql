SELECT *
FROM   IDENTITY_PAY_INFO_CFV
WHERE  party_type_db = 'CUSTOMER'
ORDER  BY identity, company
