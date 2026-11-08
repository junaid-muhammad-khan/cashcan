import * as file from "./users-file";
import * as dbx from "./users-databricks";

export type { UserRecord } from "./users-file";
export { EmailTakenError } from "./users-file";

// Databricks when DATABRICKS_HOST/TOKEN/WAREHOUSE_ID are set (production); otherwise the local JSON file (dev).
const useDatabricks = () => Boolean(process.env.DATABRICKS_HOST && process.env.DATABRICKS_TOKEN && process.env.DATABRICKS_WAREHOUSE_ID);
const store = () => (useDatabricks() ? dbx : file);

export const findUserByEmail = (email: string) => store().findUserByEmail(email);
export const findUserById = (id: string) => store().findUserById(id);
export const findUserByResetHash = (hash: string) => store().findUserByResetHash(hash);
export const createUser = (...a: Parameters<typeof file.createUser>) => store().createUser(...a);
export const updateUser = (...a: Parameters<typeof file.updateUser>) => store().updateUser(...a);
