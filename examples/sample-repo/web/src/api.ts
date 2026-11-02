/** Loads orders from a local JSON export. */
import { readFileSync } from "fs";
import { Order } from "./types";

/** Read all orders from a JSON file on disk. */
export function loadOrders(path: string): Order[] {
  const raw = readFileSync(path, "utf-8");
  return JSON.parse(raw) as Order[];
}

export function findOrder(orders: Order[], id: string): Order | undefined {
  return orders.find((order) => order.id === id);
}
