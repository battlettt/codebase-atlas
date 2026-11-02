/** Shared order types for the cart. */

export type Status = "open" | "paid" | "shipped";

/** One line in a customer's order. */
export interface OrderLine {
  sku: string;
  quantity: number;
  unitPrice: number;
}

export interface Order {
  id: string;
  status: Status;
  lines: OrderLine[];
}
