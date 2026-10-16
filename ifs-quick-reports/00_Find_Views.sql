-- Run this if a report fails with "table or view does not exist".
-- Lists the *_CFV views (base + customization + configuration columns) and related views in your database.
SELECT view_name
FROM   all_views
WHERE  view_name LIKE '%\_CFV' ESCAPE '\'
   AND (view_name LIKE 'SUPPLIER%'
     OR view_name LIKE 'SUPP\_%' ESCAPE '\'
     OR view_name LIKE 'CUSTOMER%'
     OR view_name LIKE 'CUST\_ORD\_CUSTOMER%' ESCAPE '\'
     OR view_name LIKE 'IDENTITY\_%' ESCAPE '\'
     OR view_name LIKE 'SRM\_SUPP%' ESCAPE '\'
     OR view_name = 'COMM_METHOD_CFV')
ORDER  BY view_name
