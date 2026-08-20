// Session/token storage via expo-secure-store (Keychain / Keystore backed).
import * as SecureStore from "expo-secure-store";
export const setToken = (t: string) => SecureStore.setItemAsync("session", t);
export const getToken = () => SecureStore.getItemAsync("session");
