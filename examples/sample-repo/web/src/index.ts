/** Entry point: prints the discounted total of open orders. */
import { CartService, applyDiscount } from "./cart";

const service = new CartService(process.argv[2] ?? "orders.json");
console.log(applyDiscount(service.openTotal()).toFixed(2));
