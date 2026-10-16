# IFS Quick Reports for the duplication tool

Create one Quick Report per query below in IFS (Solution Manager > Quick Reports), name it **exactly** as the heading,
run it, and use *Export to Excel*. On the Suppliers / Customers page choose **Quick report files** and add all the
exports at once. The report code at the start of the file name (`SUP01`, `CUS04`, ...) maps each file to its data set.

The queries read the `_CFV` views, which carry every column: base + customization (custom fields) + configuration.
Column names such as `SUPPLIER_ID` become `SupplierId` automatically; plumbing columns (`OBJID`, `OBJVERSION`,
`OBJKEY`, `*_DB`, ...) are dropped on import. Custom fields keep their `CF$_` names.

**Status.** *Your view (_CFV)* = the LU you confirmed, read through its `_CFV` view. *Verify view name* = best guess
not confirmed against a live database; run `00_Find_Views.sql` to see the real names and adjust the `FROM` line.

## Supplier

### SUP01_General  (Your view (_CFV))
Feeds: general

```sql
SELECT *
FROM   SUPPLIER_INFO_GENERAL_CFV
ORDER  BY supplier_id
```

### SUP02_SupplierInfoAddresses  (Your view (_CFV))
Feeds: SupplierInfoAddresses

```sql
SELECT *
FROM   SUPPLIER_INFO_ADDRESS_CFV
ORDER  BY supplier_id, address_id
```

### SUP03_AddressTypes  (Verify view name)
Feeds: SupplierInfoAddresses > AddressTypes

```sql
SELECT *
FROM   SUPPLIER_INFO_ADDRESS_TYPE
ORDER  BY supplier_id, address_id
```

### SUP04_AddressCommunicationMethods  (Verify view name)
Feeds: SupplierInfoAddresses > AddressCommunicationMethods

```sql
SELECT *
FROM   COMM_METHOD
WHERE  identity IN (SELECT supplier_id FROM SUPPLIER_INFO_GENERAL) AND address_id IS NOT NULL
ORDER  BY identity, address_id
```

> COMM_METHOD_CFV does not exist in this database, so the base view is used (no custom fields on communication methods).

### SUP05_SupplierInfoContacts  (Your view (_CFV))
Feeds: SupplierInfoAddresses > SupplierInfoContacts

```sql
SELECT *
FROM   SUPPLIER_INFO_CONTACT_CFV
```

### SUP06_SupplierDeliveryTaxInfoArray  (Verify view name)
Feeds: SupplierInfoAddresses > SupplierDeliveryTaxInfoArray

```sql
SELECT *
FROM   SUPPLIER_DELIVERY_TAX_INFO
```

### SUP07_SupplierDeliveryTaxCodeArray  (Verify view name)
Feeds: SupplierInfoAddresses > SupplierDeliveryTaxInfoArray > SupplierDeliveryTaxCodeArray

```sql
SELECT *
FROM   SUPPLIER_DELIVERY_TAX_CODE
```

### SUP08_SupplierAddresses  (Verify view name)
Feeds: SupplierInfoAddresses > SupplierAddresses

```sql
SELECT *
FROM   SUPPLIER_ADDRESS
```

### SUP09_SuppOutboundAddrInfoArray  (Verify view name)
Feeds: SupplierInfoAddresses > SuppOutboundAddrInfoArray

```sql
SELECT *
FROM   SUPP_OUTBOUND_ADDR_INFO
```

### SUP10_MessageSetups  (Your view (_CFV))
Feeds: MessageSetups

```sql
SELECT *
FROM   SUPPLIER_INFO_MSG_SETUP_CFV
```

### SUP11_SupplierInvoiceCompanies  (Your view (_CFV))
Feeds: SupplierInvoiceCompanies

```sql
SELECT *
FROM   IDENTITY_INVOICE_INFO_CFV
WHERE  party_type_db = 'SUPPLIER'
ORDER  BY identity, company
```

### SUP12_SupplierPayments  (Your view (_CFV))
Feeds: SupplierPayments

```sql
SELECT *
FROM   IDENTITY_PAY_INFO_CFV
WHERE  party_type_db = 'SUPPLIER'
ORDER  BY identity, company
```

### SUP13_PaymentWayArray  (Verify view name)
Feeds: SupplierPayments > PaymentWayArray

```sql
SELECT *
FROM   IDENTITY_PAY_WAY
WHERE  party_type_db = 'SUPPLIER'
ORDER  BY identity, company
```

### SUP14_SupplierPurchases  (Your view (_CFV))
Feeds: SupplierPurchases

```sql
SELECT *
FROM   SUPPLIER_CFV
ORDER  BY vendor_no
```

> Purchase supplier data is keyed by VENDOR_NO (= the supplier ID); the import maps it to SupplierId.

### SUP15_SrmSupplierInfoArray  (Your view (_CFV))
Feeds: SrmSupplierInfoArray

```sql
SELECT *
FROM   SRM_SUPP_INFO_CFV
```

> Add-on SRM supplier data (SrmSuppInfo). Maps to the SrmSupplierInfoArray data set.

## Customer

### CUS01_General  (Verify view name)
Feeds: general

```sql
SELECT *
FROM   CUSTOMER_INFO_CFV
ORDER  BY customer_id
```

### CUS02_CustomerInfoAddresses  (Verify view name)
Feeds: CustomerInfoAddresses

```sql
SELECT *
FROM   CUSTOMER_INFO_ADDRESS_CFV
ORDER  BY customer_id, address_id
```

### CUS03_AddressTypes  (Verify view name)
Feeds: CustomerInfoAddresses > AddressTypes

```sql
SELECT *
FROM   CUSTOMER_INFO_ADDRESS_TYPE
ORDER  BY customer_id, address_id
```

### CUS04_CustomerTaxInfoArray  (Verify view name)
Feeds: CustomerInfoAddresses > CustomerTaxInfoArray

```sql
SELECT *
FROM   CUSTOMER_TAX_INFO
```

### CUS05_CustomerDeliveryTaxInfoArray  (Verify view name)
Feeds: CustomerInfoAddresses > CustomerTaxInfoArray > CustomerDeliveryTaxInfoArray

```sql
SELECT *
FROM   CUSTOMER_DELIVERY_TAX_INFO
```

### CUS06_CustomerDeliveryTaxCodes  (Verify view name)
Feeds: CustomerInfoAddresses > CustomerTaxInfoArray > CustomerDeliveryTaxInfoArray > CustomerDeliveryTaxCodes

```sql
SELECT *
FROM   CUSTOMER_DELIVERY_TAX_CODES
```

### CUS07_SalesCustomerAddressArray  (Verify view name)
Feeds: CustomerInfoAddresses > SalesCustomerAddressArray

```sql
SELECT *
FROM   CUST_ORD_CUSTOMER_ADDRESS
```

> Sales address data is keyed by CUSTOMER_NO / ADDR_NO; the import maps them to CustomerId / AddressId.

### CUS08_CustomerInvoiceCompanies  (Verify view name)
Feeds: CustomerInvoiceCompanies

```sql
SELECT *
FROM   IDENTITY_INVOICE_INFO_CFV
WHERE  party_type_db = 'CUSTOMER'
ORDER  BY identity, company
```

### CUS09_CustomerPayments  (Verify view name)
Feeds: CustomerPayments

```sql
SELECT *
FROM   IDENTITY_PAY_INFO_CFV
WHERE  party_type_db = 'CUSTOMER'
ORDER  BY identity, company
```

### CUS10_CustomerCreditInfoArray  (Verify view name)
Feeds: CustomerCreditInfoArray

```sql
SELECT *
FROM   CUSTOMER_CREDIT_INFO
```

### CUS11_CustOrdCustomers  (Verify view name)
Feeds: CustOrdCustomers

```sql
SELECT *
FROM   CUST_ORD_CUSTOMER_CFV
ORDER  BY customer_id
```
