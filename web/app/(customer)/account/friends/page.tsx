'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import { useLocale } from '../../../../components/locale-provider';
import {
  disableCustomerFriendLink,
  getCustomerFriendLink,
  listCustomerFriends,
  removeCustomerFriend,
  resetCustomerFriendLink,
  type CustomerFriend,
  type CustomerFriendLink,
} from '../../../../lib/customer-friends';
import {
  createFriendship,
  getLinkSessionStatus,
} from '../../../../lib/user-link-api';
import type { PublicLinkSessionStatusResponse } from '../../../../lib/api-types';

const AUTH_ERRORS = new Set(['invalid_or_expired_token', 'unauthorized', 'account_not_found', 'claim_inactive']);
const LOGIN_NEXT_PATH = '/auth/login?next=/account/friends';

type FriendCopy = ReturnType<typeof useLocale>['messages']['customerPages']['friends'];

function loginNextPath(inviteToken: string): string {
  if (!inviteToken) {
    return LOGIN_NEXT_PATH;
  }
  const next = `/account/friends?link_session=${encodeURIComponent(inviteToken)}`;
  return `/auth/login?next=${encodeURIComponent(next)}`;
}

function CustomerFriendsPageContent() {
  const { replace } = useRouter();
  const searchParams = useSearchParams();
  const { messages } = useLocale();
  const copy = messages.customerPages.friends;
  const inviteToken = searchParams.get('link_session')?.trim() ?? '';
  const [friendLink, setFriendLink] = useState<CustomerFriendLink | null>(null);
  const [friends, setFriends] = useState<CustomerFriend[]>([]);
  const [linkSession, setLinkSession] = useState<PublicLinkSessionStatusResponse | null>(null);
  const [linkSessionFailed, setLinkSessionFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const requestIdRef = useRef(0);

  const inviteFriend = useMemo(() => {
    if (!linkSession) {
      return null;
    }
    return friends.find((friend) => friend.counterpartAccountId === linkSession.providerAccountId) ?? null;
  }, [friends, linkSession]);
  const canCreateFriendship = Boolean(linkSession && linkSession.status === 'opened' && !inviteFriend);

  const loadData = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError('');

    try {
      const [linkRes, friendsRes, linkSessionRes] = await Promise.all([
        getCustomerFriendLink(),
        listCustomerFriends(),
        inviteToken ? getLinkSessionStatus(inviteToken) : Promise.resolve(null),
      ]);
      if (requestId !== requestIdRef.current) {
        return false;
      }
      if (!linkRes.ok) {
        if (AUTH_ERRORS.has(linkRes.error)) {
          replace(loginNextPath(inviteToken));
          return false;
        }
        setError(copy.loadFailure);
        return false;
      }
      if (!friendsRes.ok) {
        if (AUTH_ERRORS.has(friendsRes.error)) {
          replace(loginNextPath(inviteToken));
          return false;
        }
        setError(copy.loadFailure);
        return false;
      }
      setFriendLink(linkRes.data);
      setFriends(friendsRes.data);
      if (linkSessionRes) {
        setLinkSession(linkSessionRes.ok ? linkSessionRes.data : null);
        setLinkSessionFailed(!linkSessionRes.ok);
      } else {
        setLinkSession(null);
        setLinkSessionFailed(false);
      }
      return true;
    } catch {
      if (requestId === requestIdRef.current) {
        setError(copy.loadFailure);
      }
      return false;
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [copy.loadFailure, inviteToken, replace]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function copyLink() {
    if (!friendLink) {
      return;
    }
    setError('');
    setNotice('');
    try {
      await navigator.clipboard.writeText(friendLink.url);
      setNotice(copy.copied);
    } catch {
      setError(copy.actionFailure);
    }
  }

  async function runInviteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!inviteToken || !canCreateFriendship) {
      return;
    }

    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await createFriendship({ token: inviteToken });
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(inviteToken));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      setNotice(copy.inviteSent);
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  async function resetLink() {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await resetCustomerFriendLink();
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(inviteToken));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  async function disableLink() {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await disableCustomerFriendLink();
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(inviteToken));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      setFriendLink(null);
      setNotice(copy.linkDisabled);
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  async function removeFriend(friendshipId: string) {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await removeCustomerFriend(friendshipId);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(inviteToken));
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
    }
  }

  return (
    <section className="customer-view customer-view--wide customer-friends-page">
      <div className="customer-panel customer-panel--wide customer-friends-panel">
        <div className="customer-panel__head">
          <p className="customer-panel__eyebrow">{copy.eyebrow}</p>
          <h1 className="customer-panel__title">{copy.title}</h1>
          <p className="customer-panel__body">{copy.description}</p>
        </div>

        {loading ? <p className="customer-inline-note">{copy.loading}</p> : null}
        {error ? <p className="customer-inline-note customer-inline-note--error">{error}</p> : null}
        {notice ? <p className="customer-inline-note">{notice}</p> : null}

        <section className="customer-friends-section" aria-labelledby="friend-link-title">
          <div>
            <h2 id="friend-link-title">{copy.linkTitle}</h2>
            <p>{copy.linkDescription}</p>
          </div>
          <div className="customer-friend-link-box">
            <span>{friendLink?.url ?? ''}</span>
          </div>
          <div className="customer-action-row">
            <button
              type="button"
              className="customer-action customer-action--primary"
              onClick={copyLink}
              disabled={!friendLink || actionPending}
            >
              {copy.copyLink}
            </button>
            <button
              type="button"
              className="customer-action customer-action--secondary"
              onClick={resetLink}
              disabled={!friendLink || actionPending}
            >
              {copy.resetLink}
            </button>
            <button
              type="button"
              className="customer-action customer-action--secondary"
              onClick={disableLink}
              disabled={!friendLink || actionPending}
            >
              {copy.disableLink}
            </button>
          </div>
        </section>

        {inviteToken ? (
          <section className="customer-friends-section customer-friend-invite" aria-labelledby="friend-invite-title">
            <div>
              <h2 id="friend-invite-title">{copy.inviteTitle}</h2>
              <p>{copy.inviteDescription}</p>
            </div>
            {linkSessionFailed ? (
              <p className="customer-inline-note customer-inline-note--error">{copy.inviteLoadFailure}</p>
            ) : null}
            {linkSession ? (
              <>
                <div className="customer-friend-link-box">
                  <span>{copy.inviteTargetLabel}: {linkSession.providerAccountId}</span>
                </div>
                {inviteFriend ? (
                  <p className="customer-inline-note">{copy.inviteAlreadyFriend}</p>
                ) : canCreateFriendship ? (
                  <form className="customer-friend-invite__form" onSubmit={runInviteSubmit}>
                    <button type="submit" className="customer-action customer-action--primary" disabled={actionPending}>
                      {actionPending ? copy.inviteSending : copy.inviteSend}
                    </button>
                  </form>
                ) : (
                  <p className="customer-inline-note customer-inline-note--error">{copy.inviteUnavailable}</p>
                )}
              </>
            ) : null}
          </section>
        ) : null}

        <section className="customer-friends-section" aria-labelledby="current-friends-title">
          <h2 id="current-friends-title">{copy.friendsTitle}</h2>
          {friends.length === 0 ? (
            <p className="customer-friends-empty">{copy.emptyFriends}</p>
          ) : (
            <div className="customer-friends-list">
              {friends.map((friend) => (
                <article className="customer-friend-row" key={friend.id}>
                  <div>
                    <strong>{friend.counterpartProfile?.displayName || copy.unknownFriend}</strong>
                    <span>{friend.counterpartAccountId}</span>
                  </div>
                  <div className="customer-friend-row__actions">
                    <button
                      type="button"
                      className="customer-action customer-action--secondary"
                      onClick={() => void removeFriend(friend.id)}
                      disabled={actionPending}
                    >
                      {copy.removeFriend}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

export default function CustomerFriendsPage() {
  return (
    <Suspense fallback={null}>
      <CustomerFriendsPageContent />
    </Suspense>
  );
}
