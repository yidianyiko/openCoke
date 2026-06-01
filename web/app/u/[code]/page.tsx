import Link from 'next/link';
import { fetchUserLink } from '../../../lib/user-link-api';

function dashboardAuthHref(path: '/auth/login' | '/auth/register', code: string): string {
  const next = `/account/friends?join=${encodeURIComponent(code)}`;
  return `${path}?next=${encodeURIComponent(next)}`;
}

export default async function UserLinkPage({
  params,
}: {
  params: Promise<{ code: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { code } = await params;
  const result = await fetchUserLink(code);

  if (!result.ok) {
    return (
      <main className="coke-site public-user-link">
        <section className="public-user-link__panel" aria-labelledby="user-link-inactive-title">
          <h1 id="user-link-inactive-title">Link no longer active</h1>
          <p>This user link cannot be used to add a friend.</p>
        </section>
      </main>
    );
  }

  const link = result.data;
  const { profile } = link;

  return (
    <main className="coke-site public-user-link">
      <section className="public-user-link__panel" aria-labelledby="user-link-title">
        {profile.avatarUrl ? (
          <img
            className="public-user-link__avatar"
            src={profile.avatarUrl}
            alt=""
            width={72}
            height={72}
          />
        ) : null}
        <h1 id="user-link-title">{profile.displayName}</h1>
        {profile.tagline ? <p>{profile.tagline}</p> : null}
        <img
          className="public-user-link__qr"
          src={`/u/${encodeURIComponent(code)}/qr`}
          alt=""
          width={160}
          height={160}
        />
        <div className="public-user-link__actions">
          <Link href={dashboardAuthHref('/auth/login', code)}>Log in to add friend</Link>
          <Link href={dashboardAuthHref('/auth/register', code)}>Create account to add friend</Link>
        </div>
      </section>
    </main>
  );
}
