// Device biometric gate using expo-local-authentication.
// Gates access to an already-authenticated session; it is NOT the identity check.
import * as LocalAuthentication from "expo-local-authentication";

export async function requireBiometric(): Promise<boolean> {
  const has = await LocalAuthentication.hasHardwareAsync();
  if (!has) return true; // fall back to session auth on devices without biometrics
  const res = await LocalAuthentication.authenticateAsync({
    promptMessage: "Unlock Disciplined Edge",
  });
  return res.success;
}
