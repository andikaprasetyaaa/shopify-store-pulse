GET_SHOP = """
query GetShop {
  shop {
    name
  }
}
""".strip()


GET_ACCESS_SCOPES = """
query AccessScopeList {
  currentAppInstallation {
    accessScopes {
      handle
    }
  }
}
""".strip()


GET_PRODUCT_VARIANTS = """
query GetProductVariants(
  $first: Int!,
  $after: String
) {
  productVariants(
    first: $first,
    after: $after
  ) {
    nodes {
      id
      title
      sku
      price

      inventoryItem {
        id
      }

      product {
        id
        title
        handle
        status
        vendor
        productType
      }
    }

    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()


GET_INVENTORY_VARIANTS = """
query GetInventoryVariants(
  $first: Int!,
  $after: String
) {
  productVariants(
    first: $first,
    after: $after
  ) {
    nodes {
      id
      sku

      product {
        id
        title
      }

      inventoryItem {
        id
        tracked

        inventoryLevels(
          first: 250
        ) {
          nodes {
            id

            location {
              id
              name
            }

            quantities(
              names: ["available"]
            ) {
              name
              quantity
            }
          }

          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }

    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()


GET_ORDERS = """
query GetOrders(
  $first: Int!,
  $after: String,
  $query: String
) {
  orders(
    first: $first,
    after: $after,
    query: $query,
    sortKey: CREATED_AT,
    reverse: true
  ) {
    nodes {
      id
      name
      createdAt
      updatedAt
      cancelledAt
      displayFinancialStatus
      displayFulfillmentStatus

      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }

      lineItems(
        first: 250
      ) {
        nodes {
          id
          name
          title
          sku
          quantity
          currentQuantity

          product {
            id
          }

          variant {
            id
          }

          originalTotalSet {
            shopMoney {
              amount
              currencyCode
            }
          }

          priceAfterAllDiscountsBeforeTaxesSet {
            shopMoney {
              amount
              currencyCode
            }
          }
        }

        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }

    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".strip()


RUN_SHOPIFYQL = """
query RunShopifyQL(
  $shopifyql: String!
) {
  shopifyqlQuery(
    query: $shopifyql
  ) {
    tableData {
      columns {
        name
        dataType
        displayName
      }

      rows
    }

    parseErrors
  }
}
""".strip()