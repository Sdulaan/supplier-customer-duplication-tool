// Entity definitions and the fields shown when comparing records.

export const ENTITIES = [
  { id: 'supplier', label: 'Supplier', idKey: 'supplierId', description: 'Supplier master data (name, tax no., address, bank)' },
  { id: 'customer', label: 'Customer', idKey: 'customerId', description: 'Customer master data (name, tax no., address, contact)' }
]

export const FIELDS = {
  supplier: [
    ['supplierId', 'Supplier ID'],
    ['name', 'Name'],
    ['taxNo', 'Tax / Reg. No.'],
    ['address', 'Address'],
    ['city', 'City'],
    ['country', 'Country'],
    ['email', 'Email']
  ],
  customer: [
    ['customerId', 'Customer ID'],
    ['name', 'Name'],
    ['taxNo', 'Tax / Reg. No.'],
    ['address', 'Address'],
    ['city', 'City'],
    ['country', 'Country'],
    ['email', 'Email']
  ]
}
