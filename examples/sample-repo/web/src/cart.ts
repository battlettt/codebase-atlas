/** Cart math: totals and discounts for orders. */
import { Order, OrderLine } from "./types";
import { loadOrders } from "./api";

/** Sum the price of every line in an order. */
export function orderTotal(order: Order): number {
  return order.lines.reduce((sum: number, line: OrderLine) => sum + lineTotal(line), 0);
}

function lineTotal(line: OrderLine): number {
  return line.quantity * line.unitPrice;
}

// FIXME: discounts are hard-coded; read them from configuration instead.
export function applyDiscount(total: number): number {
  return total > 100 ? total * 0.9 : total;
}

/** Computes totals for the orders stored in one file. */
export class CartService {
  constructor(private readonly path: string) {}

  /** Total value of all open orders. */
  openTotal(): number {
    const orders = loadOrders(this.path);
    return orders
      .filter((order) => order.status === "open")
      .reduce((sum, order) => sum + orderTotal(order), 0);
  }
}
