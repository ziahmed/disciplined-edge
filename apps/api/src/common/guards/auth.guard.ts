import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";

/**
 * Verifies the session from the identity provider (Clerk/Supabase) and attaches
 * the user to the request. Authorization (who can see which portfolio) lives in
 * each service, not here. Stub — wire to the provider's token verification.
 */
@Injectable()
export class AuthGuard implements CanActivate {
  canActivate(_ctx: ExecutionContext): boolean {
    // TODO: verify bearer token, set request.user. Reject if missing/invalid.
    throw new UnauthorizedException("AuthGuard not yet implemented");
  }
}
