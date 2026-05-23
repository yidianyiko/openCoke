# Friend Management Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/account/friends`, a dedicated customer web page for managing friend links, incoming requests, outgoing requests, and current friends.

**Architecture:** Reuse the existing Gateway scheduling API without backend route changes. Add a focused web-client wrapper, wire customer navigation/i18n, then implement one client page that fetches the friend link, requests, and friends and refreshes data after mutations.

**Tech Stack:** Next.js App Router, React client components, Vitest + jsdom, existing `customerApi`, existing `LocaleProvider` messages, existing customer shell CSS.

---

## File Structure

- Create `gateway/packages/web/lib/customer-friends.ts`: typed web-client wrapper around existing `/api/customer/scheduling/*` endpoints.
- Create `gateway/packages/web/lib/customer-friends.test.ts`: unit tests for the wrapper endpoint paths and encoded identifiers.
- Modify `gateway/packages/web/components/customer-shell.tsx`: add the `/account/friends` navigation item in English and Chinese.
- Modify `gateway/packages/web/app/(customer)/account/layout.test.tsx`: assert the new nav item exists.
- Modify `gateway/packages/web/lib/i18n.ts`: add `customerPages.friends` message shape and English/Chinese copy.
- Create `gateway/packages/web/app/(customer)/account/friends/page.tsx`: client page for friend-link, request, and friendship management.
- Create `gateway/packages/web/app/(customer)/account/friends/page.test.tsx`: page behavior tests.
- Modify `gateway/packages/web/app/public-site.css`: focused classes for the friend page using the existing customer-page style vocabulary.

## Data Shapes

Use these frontend-only types in `customer-friends.ts`:

```ts
export interface CustomerFriendLink {
  code: string;
  status: 'active';
  url: string;
  qrUrl: string;
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
}

export interface CustomerFriendRequest {
  id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'cancelled';
  direction: 'incoming' | 'outgoing';
  counterpartAccountId: string;
}

export interface CustomerFriend {
  id: string;
  status: string;
  counterpartAccountId: string;
  counterpartProfile?: {
    displayName: string;
    avatarUrl: string | null;
  };
}
```

The backend route already derives `direction` in `customer-scheduling-routes.ts`; the page should use that field instead of re-deriving direction from hidden IDs.

### Task 1: Customer Friends API Wrapper

**Files:**
- Create: `gateway/packages/web/lib/customer-friends.ts`
- Create: `gateway/packages/web/lib/customer-friends.test.ts`

- [ ] **Step 1: Write the failing wrapper tests**

Create `gateway/packages/web/lib/customer-friends.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { customerApi } from './customer-api';
import {
  acceptCustomerFriendRequest,
  cancelCustomerFriendRequest,
  disableCustomerFriendLink,
  getCustomerFriendLink,
  listCustomerFriendRequests,
  listCustomerFriends,
  rejectCustomerFriendRequest,
  removeCustomerFriend,
  resetCustomerFriendLink,
} from './customer-friends';

vi.mock('./customer-api', () => ({
  customerApi: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const apiMock = vi.mocked(customerApi);

afterEach(() => {
  vi.clearAllMocks();
});

describe('customer friends wrappers', () => {
  it('reads the current friend link, friend requests, and friends from scheduling endpoints', async () => {
    apiMock.get.mockResolvedValue({ ok: true, data: null });

    await getCustomerFriendLink();
    await listCustomerFriendRequests();
    await listCustomerFriends();

    expect(apiMock.get).toHaveBeenNthCalledWith(1, '/api/customer/scheduling/user-link');
    expect(apiMock.get).toHaveBeenNthCalledWith(2, '/api/customer/scheduling/friend-requests');
    expect(apiMock.get).toHaveBeenNthCalledWith(3, '/api/customer/scheduling/friends');
  });

  it('mutates the current friend link through reset and disable endpoints', async () => {
    apiMock.post.mockResolvedValue({ ok: true, data: null });

    await resetCustomerFriendLink();
    await disableCustomerFriendLink();

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/customer/scheduling/user-link/reset');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/customer/scheduling/user-link/disable');
  });

  it('runs friend request actions with encoded request ids', async () => {
    apiMock.post.mockResolvedValue({ ok: true, data: { id: 'fr/1', status: 'pending' } });

    await acceptCustomerFriendRequest('fr/1');
    await rejectCustomerFriendRequest('fr/1');
    await cancelCustomerFriendRequest('fr/1');

    expect(apiMock.post).toHaveBeenNthCalledWith(1, '/api/customer/scheduling/friend-requests/fr%2F1/accept');
    expect(apiMock.post).toHaveBeenNthCalledWith(2, '/api/customer/scheduling/friend-requests/fr%2F1/reject');
    expect(apiMock.post).toHaveBeenNthCalledWith(3, '/api/customer/scheduling/friend-requests/fr%2F1/cancel');
  });

  it('removes a friendship with an encoded friendship id', async () => {
    apiMock.delete.mockResolvedValueOnce({ ok: true, data: { id: 'fs/1', status: 'removed' } });

    await removeCustomerFriend('fs/1');

    expect(apiMock.delete).toHaveBeenCalledWith('/api/customer/scheduling/friends/fs%2F1');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- lib/customer-friends.test.ts
```

Expected: FAIL because `./customer-friends` does not exist.

- [ ] **Step 3: Implement the wrapper**

Create `gateway/packages/web/lib/customer-friends.ts`:

```ts
import type { ApiResponse } from '../../shared/src/types/api';
import { customerApi } from './customer-api';

export interface CustomerFriendLink {
  code: string;
  status: 'active';
  url: string;
  qrUrl: string;
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
}

export interface CustomerFriendRequest {
  id: string;
  status: 'pending' | 'accepted' | 'rejected' | 'cancelled';
  direction: 'incoming' | 'outgoing';
  counterpartAccountId: string;
}

export interface CustomerFriend {
  id: string;
  status: string;
  counterpartAccountId: string;
  counterpartProfile?: {
    displayName: string;
    avatarUrl: string | null;
  };
}

type FriendRequestActionResult = {
  id: string;
  status: string;
};

export function getCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.get<ApiResponse<CustomerFriendLink>>('/api/customer/scheduling/user-link');
}

export function resetCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi.post<ApiResponse<CustomerFriendLink>>('/api/customer/scheduling/user-link/reset');
}

export function disableCustomerFriendLink(): Promise<ApiResponse<{ count: number }>> {
  return customerApi.post<ApiResponse<{ count: number }>>('/api/customer/scheduling/user-link/disable');
}

export function listCustomerFriendRequests(): Promise<ApiResponse<CustomerFriendRequest[]>> {
  return customerApi.get<ApiResponse<CustomerFriendRequest[]>>('/api/customer/scheduling/friend-requests');
}

export function acceptCustomerFriendRequest(requestId: string): Promise<ApiResponse<FriendRequestActionResult>> {
  return customerApi.post<ApiResponse<FriendRequestActionResult>>(
    `/api/customer/scheduling/friend-requests/${encodeURIComponent(requestId)}/accept`,
  );
}

export function rejectCustomerFriendRequest(requestId: string): Promise<ApiResponse<FriendRequestActionResult>> {
  return customerApi.post<ApiResponse<FriendRequestActionResult>>(
    `/api/customer/scheduling/friend-requests/${encodeURIComponent(requestId)}/reject`,
  );
}

export function cancelCustomerFriendRequest(requestId: string): Promise<ApiResponse<FriendRequestActionResult>> {
  return customerApi.post<ApiResponse<FriendRequestActionResult>>(
    `/api/customer/scheduling/friend-requests/${encodeURIComponent(requestId)}/cancel`,
  );
}

export function listCustomerFriends(): Promise<ApiResponse<CustomerFriend[]>> {
  return customerApi.get<ApiResponse<CustomerFriend[]>>('/api/customer/scheduling/friends');
}

export function removeCustomerFriend(friendshipId: string): Promise<ApiResponse<FriendRequestActionResult>> {
  return customerApi.delete<ApiResponse<FriendRequestActionResult>>(
    `/api/customer/scheduling/friends/${encodeURIComponent(friendshipId)}`,
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- lib/customer-friends.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gateway/packages/web/lib/customer-friends.ts gateway/packages/web/lib/customer-friends.test.ts
git commit -m "feat: add customer friend api wrappers"
```

### Task 2: Navigation And Friend Page Copy

**Files:**
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/layout.test.tsx`
- Modify: `gateway/packages/web/lib/i18n.ts`
- Test: `gateway/packages/web/app/(customer)/account/layout.test.tsx`
- Test: `gateway/packages/web/lib/i18n.test.ts`

- [ ] **Step 1: Write the failing navigation assertion**

In `gateway/packages/web/app/(customer)/account/layout.test.tsx`, add this assertion near the existing customer shell nav assertions:

```ts
expect(container.querySelector('a[href="/account/friends"]')).toBeTruthy();
expect(container.textContent).toContain('好友');
```

- [ ] **Step 2: Run the layout test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/account/layout.test.tsx'
```

Expected: FAIL because `/account/friends` is not in `CUSTOMER_NAV`.

- [ ] **Step 3: Add the navigation entry**

In `gateway/packages/web/components/customer-shell.tsx`, add the English item immediately before Reminders:

```ts
{ href: '/account/friends', label: 'Friends' },
```

Add the Chinese item at the matching position:

```ts
{ href: '/account/friends', label: '好友' },
```

- [ ] **Step 4: Add the friend-page message type**

In `gateway/packages/web/lib/i18n.ts`, extend `CustomerPagesMessages` after `channelsIndex` or near the account-page message groups:

```ts
  friends: {
    eyebrow: string;
    title: string;
    description: string;
    linkTitle: string;
    linkDescription: string;
    copyLink: string;
    copied: string;
    resetLink: string;
    disableLink: string;
    linkDisabled: string;
    incomingTitle: string;
    outgoingTitle: string;
    friendsTitle: string;
    emptyIncoming: string;
    emptyOutgoing: string;
    emptyFriends: string;
    loading: string;
    loadFailure: string;
    actionFailure: string;
    accept: string;
    reject: string;
    cancelRequest: string;
    removeFriend: string;
    pending: string;
    accepted: string;
    rejected: string;
    cancelled: string;
    unknownFriend: string;
  };
```

- [ ] **Step 5: Add English copy**

In the English `customerPages` object, add:

```ts
      friends: {
        eyebrow: 'Friends',
        title: 'Friend management',
        description: 'Share your add-friend link, review requests, and manage current friends.',
        linkTitle: 'My friend link',
        linkDescription: 'Share this URL with someone who should be able to send you a friend request.',
        copyLink: 'Copy link',
        copied: 'Link copied.',
        resetLink: 'Reset link',
        disableLink: 'Disable current link',
        linkDisabled: 'The current link was disabled. A new link can be created when you refresh this page.',
        incomingTitle: 'Incoming requests',
        outgoingTitle: 'Outgoing requests',
        friendsTitle: 'Current friends',
        emptyIncoming: 'No incoming friend requests.',
        emptyOutgoing: 'No outgoing friend requests.',
        emptyFriends: 'No friends yet.',
        loading: 'Loading friend data...',
        loadFailure: 'Unable to load friend data right now.',
        actionFailure: 'Unable to update friend data right now.',
        accept: 'Accept',
        reject: 'Reject',
        cancelRequest: 'Cancel request',
        removeFriend: 'Remove friend',
        pending: 'Pending',
        accepted: 'Accepted',
        rejected: 'Rejected',
        cancelled: 'Cancelled',
        unknownFriend: 'Unknown account',
      },
```

- [ ] **Step 6: Add Chinese copy**

In the Chinese `customerPages` object, add:

```ts
      friends: {
        eyebrow: '好友',
        title: '好友管理',
        description: '分享你的好友链接，处理好友请求，并管理当前好友。',
        linkTitle: '我的好友链接',
        linkDescription: '把这个链接发给对方，对方登录或注册后就可以向你发送好友请求。',
        copyLink: '复制链接',
        copied: '链接已复制。',
        resetLink: '重置链接',
        disableLink: '停用当前链接',
        linkDisabled: '当前链接已停用。刷新页面时可以按现有规则创建新的链接。',
        incomingTitle: '收到的请求',
        outgoingTitle: '发出的请求',
        friendsTitle: '当前好友',
        emptyIncoming: '暂无收到的好友请求。',
        emptyOutgoing: '暂无发出的好友请求。',
        emptyFriends: '暂无好友。',
        loading: '正在加载好友数据...',
        loadFailure: '暂时无法加载好友数据。',
        actionFailure: '暂时无法更新好友数据。',
        accept: '接受',
        reject: '拒绝',
        cancelRequest: '取消请求',
        removeFriend: '删除好友',
        pending: '待处理',
        accepted: '已接受',
        rejected: '已拒绝',
        cancelled: '已取消',
        unknownFriend: '未知账号',
      },
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/account/layout.test.tsx' lib/i18n.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add gateway/packages/web/components/customer-shell.tsx gateway/packages/web/app/'(customer)'/account/layout.test.tsx gateway/packages/web/lib/i18n.ts
git commit -m "feat: add friend management navigation"
```

### Task 3: Friend Management Page

**Files:**
- Create: `gateway/packages/web/app/(customer)/account/friends/page.tsx`
- Create: `gateway/packages/web/app/(customer)/account/friends/page.test.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Test: `gateway/packages/web/app/(customer)/account/friends/page.test.tsx`

- [ ] **Step 1: Write the failing page tests**

Create `gateway/packages/web/app/(customer)/account/friends/page.test.tsx`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { LocaleProvider } from '../../../../components/locale-provider';

const replaceMock = vi.hoisted(() => vi.fn());
const routerMock = vi.hoisted(() => ({ replace: replaceMock }));
const getLinkMock = vi.hoisted(() => vi.fn());
const resetLinkMock = vi.hoisted(() => vi.fn());
const disableLinkMock = vi.hoisted(() => vi.fn());
const listRequestsMock = vi.hoisted(() => vi.fn());
const acceptMock = vi.hoisted(() => vi.fn());
const rejectMock = vi.hoisted(() => vi.fn());
const cancelMock = vi.hoisted(() => vi.fn());
const listFriendsMock = vi.hoisted(() => vi.fn());
const removeMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
}));

vi.mock('../../../../lib/customer-friends', () => ({
  getCustomerFriendLink: (...args: unknown[]) => getLinkMock(...args),
  resetCustomerFriendLink: (...args: unknown[]) => resetLinkMock(...args),
  disableCustomerFriendLink: (...args: unknown[]) => disableLinkMock(...args),
  listCustomerFriendRequests: (...args: unknown[]) => listRequestsMock(...args),
  acceptCustomerFriendRequest: (...args: unknown[]) => acceptMock(...args),
  rejectCustomerFriendRequest: (...args: unknown[]) => rejectMock(...args),
  cancelCustomerFriendRequest: (...args: unknown[]) => cancelMock(...args),
  listCustomerFriends: (...args: unknown[]) => listFriendsMock(...args),
  removeCustomerFriend: (...args: unknown[]) => removeMock(...args),
}));

import FriendsPage from './page';

async function flushTicks(count: number) {
  for (let i = 0; i < count; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe('CustomerFriendsPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderPage() {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <FriendsPage />
        </LocaleProvider>,
      );
    });
  }

  beforeEach(() => {
    replaceMock.mockReset();
    getLinkMock.mockResolvedValue({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        url: 'https://kap.example/u/abc',
        qrUrl: 'https://kap.example/u/abc/qr',
        profile: { displayName: 'Alice', tagline: null, avatarUrl: null },
      },
    });
    listRequestsMock.mockResolvedValue({
      ok: true,
      data: [
        { id: 'fr_in', status: 'pending', direction: 'incoming', counterpartAccountId: 'ck_bob' },
        { id: 'fr_out', status: 'pending', direction: 'outgoing', counterpartAccountId: 'ck_cara' },
      ],
    });
    listFriendsMock.mockResolvedValue({
      ok: true,
      data: [
        {
          id: 'fs_1',
          status: 'active',
          counterpartAccountId: 'ck_dan',
          counterpartProfile: { displayName: 'Dan', avatarUrl: null },
        },
      ],
    });
    resetLinkMock.mockResolvedValue({ ok: true, data: { url: 'https://kap.example/u/new' } });
    disableLinkMock.mockResolvedValue({ ok: true, data: { count: 1 } });
    acceptMock.mockResolvedValue({ ok: true, data: { id: 'fr_in', status: 'accepted' } });
    rejectMock.mockResolvedValue({ ok: true, data: { id: 'fr_in', status: 'rejected' } });
    cancelMock.mockResolvedValue({ ok: true, data: { id: 'fr_out', status: 'cancelled' } });
    removeMock.mockResolvedValue({ ok: true, data: { id: 'fs_1', status: 'removed' } });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    vi.clearAllMocks();
  });

  it('loads friend link, incoming requests, outgoing requests, and friends', async () => {
    renderPage();
    await flushTicks(3);

    expect(getLinkMock).toHaveBeenCalled();
    expect(listRequestsMock).toHaveBeenCalled();
    expect(listFriendsMock).toHaveBeenCalled();
    expect(container.textContent).toContain('Friend management');
    expect(container.textContent).toContain('https://kap.example/u/abc');
    expect(container.textContent).toContain('Incoming requests');
    expect(container.textContent).toContain('ck_bob');
    expect(container.textContent).toContain('Outgoing requests');
    expect(container.textContent).toContain('ck_cara');
    expect(container.textContent).toContain('Current friends');
    expect(container.textContent).toContain('Dan');
  });

  it('redirects auth failures to login with the friends next path', async () => {
    getLinkMock.mockResolvedValueOnce({ ok: false, error: 'invalid_or_expired_token' });

    renderPage();
    await flushTicks(3);

    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=/account/friends');
  });

  it('runs request and friendship actions then refreshes data', async () => {
    renderPage();
    await flushTicks(3);

    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Accept')?.click();
    await flushTicks(3);
    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Reject')?.click();
    await flushTicks(3);
    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Cancel request')?.click();
    await flushTicks(3);
    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Remove friend')?.click();
    await flushTicks(3);

    expect(acceptMock).toHaveBeenCalledWith('fr_in');
    expect(rejectMock).toHaveBeenCalledWith('fr_in');
    expect(cancelMock).toHaveBeenCalledWith('fr_out');
    expect(removeMock).toHaveBeenCalledWith('fs_1');
    expect(getLinkMock).toHaveBeenCalledTimes(5);
    expect(listRequestsMock).toHaveBeenCalledTimes(5);
    expect(listFriendsMock).toHaveBeenCalledTimes(5);
  });

  it('copies, resets, and disables the friend link', async () => {
    renderPage();
    await flushTicks(3);

    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Copy link')?.click();
    await flushTicks(2);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://kap.example/u/abc');
    expect(container.textContent).toContain('Link copied.');

    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Reset link')?.click();
    await flushTicks(3);
    expect(resetLinkMock).toHaveBeenCalled();

    [...container.querySelectorAll('button')].find((button) => button.textContent === 'Disable current link')?.click();
    await flushTicks(3);
    expect(disableLinkMock).toHaveBeenCalled();
    expect(container.textContent).toContain('The current link was disabled.');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/account/friends/page.test.tsx'
```

Expected: FAIL because the page file does not exist.

- [ ] **Step 3: Implement the page**

Create `gateway/packages/web/app/(customer)/account/friends/page.tsx` with a client component that:

```ts
'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale } from '../../../../components/locale-provider';
import {
  acceptCustomerFriendRequest,
  cancelCustomerFriendRequest,
  disableCustomerFriendLink,
  getCustomerFriendLink,
  listCustomerFriendRequests,
  listCustomerFriends,
  rejectCustomerFriendRequest,
  removeCustomerFriend,
  resetCustomerFriendLink,
  type CustomerFriend,
  type CustomerFriendLink,
  type CustomerFriendRequest,
} from '../../../../lib/customer-friends';

const AUTH_ERRORS = new Set(['invalid_or_expired_token', 'unauthorized', 'account_not_found', 'claim_inactive']);
const LOGIN_NEXT_PATH = '/auth/login?next=/account/friends';

function requestLabel(request: CustomerFriendRequest, unknown: string): string {
  return request.counterpartAccountId || unknown;
}

function friendLabel(friend: CustomerFriend, unknown: string): string {
  return friend.counterpartProfile?.displayName || friend.counterpartAccountId || unknown;
}

export default function CustomerFriendsPage() {
  const { replace } = useRouter();
  const { messages } = useLocale();
  const copy = messages.customerPages.friends;
  const [friendLink, setFriendLink] = useState<CustomerFriendLink | null>(null);
  const [requests, setRequests] = useState<CustomerFriendRequest[]>([]);
  const [friends, setFriends] = useState<CustomerFriend[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const incomingRequests = useMemo(
    () => requests.filter((request) => request.direction === 'incoming'),
    [requests],
  );
  const outgoingRequests = useMemo(
    () => requests.filter((request) => request.direction === 'outgoing'),
    [requests],
  );

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [linkRes, requestsRes, friendsRes] = await Promise.all([
        getCustomerFriendLink(),
        listCustomerFriendRequests(),
        listCustomerFriends(),
      ]);
      const authError = [linkRes, requestsRes, friendsRes].find((res) => !res.ok && AUTH_ERRORS.has(res.error));
      if (authError) {
        replace(LOGIN_NEXT_PATH);
        return;
      }
      if (!linkRes.ok || !requestsRes.ok || !friendsRes.ok) {
        setError(copy.loadFailure);
        return;
      }
      setFriendLink(linkRes.data);
      setRequests(requestsRes.data);
      setFriends(friendsRes.data);
    } catch {
      setError(copy.loadFailure);
    } finally {
      setLoading(false);
    }
  }, [copy.loadFailure, replace]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function runAction(actionName: string, action: () => Promise<{ ok: true; data: unknown } | { ok: false; error: string }>) {
    setBusyAction(actionName);
    setError('');
    setNotice('');
    try {
      const result = await action();
      if (!result.ok) {
        if (AUTH_ERRORS.has(result.error)) {
          replace(LOGIN_NEXT_PATH);
          return;
        }
        setError(copy.actionFailure);
        return;
      }
      await loadData();
    } catch {
      setError(copy.actionFailure);
    } finally {
      setBusyAction(null);
    }
  }

  async function copyLink() {
    if (!friendLink?.url || !navigator.clipboard?.writeText) {
      return;
    }
    await navigator.clipboard.writeText(friendLink.url);
    setNotice(copy.copied);
  }

  async function disableLink() {
    await runAction('disable-link', disableCustomerFriendLink);
    setNotice(copy.linkDisabled);
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
        {notice ? <p className="customer-inline-note">{notice}</p> : null}
        {error ? <p className="customer-inline-note customer-inline-note--error">{error}</p> : null}

        <section className="customer-friends-section" aria-labelledby="friend-link-title">
          <div>
            <h2 id="friend-link-title">{copy.linkTitle}</h2>
            <p>{copy.linkDescription}</p>
          </div>
          {friendLink ? (
            <div className="customer-friend-link-box">
              <code>{friendLink.url}</code>
              <div className="customer-action-row">
                <button type="button" className="customer-action customer-action--primary" onClick={() => void copyLink()}>
                  {copy.copyLink}
                </button>
                <button
                  type="button"
                  className="customer-action customer-action--secondary"
                  disabled={busyAction === 'reset-link'}
                  onClick={() => void runAction('reset-link', resetCustomerFriendLink)}
                >
                  {copy.resetLink}
                </button>
                <button
                  type="button"
                  className="customer-action customer-action--secondary"
                  disabled={busyAction === 'disable-link'}
                  onClick={() => void disableLink()}
                >
                  {copy.disableLink}
                </button>
              </div>
            </div>
          ) : null}
        </section>

        <section className="customer-friends-grid">
          <RequestList
            title={copy.incomingTitle}
            emptyText={copy.emptyIncoming}
            requests={incomingRequests}
            unknown={copy.unknownFriend}
            statusCopy={copy}
            actions={(request) =>
              request.status === 'pending' ? (
                <>
                  <button type="button" onClick={() => void runAction(`accept-${request.id}`, () => acceptCustomerFriendRequest(request.id))}>
                    {copy.accept}
                  </button>
                  <button type="button" onClick={() => void runAction(`reject-${request.id}`, () => rejectCustomerFriendRequest(request.id))}>
                    {copy.reject}
                  </button>
                </>
              ) : null
            }
          />
          <RequestList
            title={copy.outgoingTitle}
            emptyText={copy.emptyOutgoing}
            requests={outgoingRequests}
            unknown={copy.unknownFriend}
            statusCopy={copy}
            actions={(request) =>
              request.status === 'pending' ? (
                <button type="button" onClick={() => void runAction(`cancel-${request.id}`, () => cancelCustomerFriendRequest(request.id))}>
                  {copy.cancelRequest}
                </button>
              ) : null
            }
          />
        </section>

        <section className="customer-friends-section" aria-labelledby="friends-title">
          <h2 id="friends-title">{copy.friendsTitle}</h2>
          {friends.length === 0 ? <p className="customer-friends-empty">{copy.emptyFriends}</p> : null}
          <div className="customer-friends-list">
            {friends.map((friend) => (
              <article key={friend.id} className="customer-friend-row">
                <div>
                  <strong>{friendLabel(friend, copy.unknownFriend)}</strong>
                  <span>{friend.counterpartAccountId}</span>
                </div>
                <button type="button" onClick={() => void runAction(`remove-${friend.id}`, () => removeCustomerFriend(friend.id))}>
                  {copy.removeFriend}
                </button>
              </article>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
```

Also define a local `RequestList` helper in the same file before the default export:

```ts
function RequestList({
  title,
  emptyText,
  requests,
  unknown,
  statusCopy,
  actions,
}: {
  title: string;
  emptyText: string;
  requests: CustomerFriendRequest[];
  unknown: string;
  statusCopy: Record<CustomerFriendRequest['status'], string>;
  actions: (request: CustomerFriendRequest) => React.ReactNode;
}) {
  return (
    <section className="customer-friends-section">
      <h2>{title}</h2>
      {requests.length === 0 ? <p className="customer-friends-empty">{emptyText}</p> : null}
      <div className="customer-friends-list">
        {requests.map((request) => (
          <article key={request.id} className="customer-friend-row">
            <div>
              <strong>{requestLabel(request, unknown)}</strong>
              <span>{statusCopy[request.status]}</span>
            </div>
            <div className="customer-friend-row__actions">{actions(request)}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
```

Import `type ReactNode` from React if using `React.ReactNode` is not already available:

```ts
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
```

Then use `actions: (request: CustomerFriendRequest) => ReactNode`.

- [ ] **Step 4: Add page CSS**

Append focused styles to `gateway/packages/web/app/public-site.css` near the existing customer account page styles:

```css
.coke-site .customer-friends-page {
  gap: 18px;
}

.coke-site .customer-friends-panel {
  display: grid;
  gap: 20px;
}

.coke-site .customer-friends-section {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 24px;
  border: 1px solid rgba(27, 20, 16, 0.08);
  background: rgba(255, 255, 255, 0.72);
}

.coke-site .customer-friends-section h2 {
  margin: 0;
  color: var(--ink-1000);
  font-size: 20px;
  line-height: 1.2;
}

.coke-site .customer-friends-section p {
  margin: 0;
  color: var(--ink-700);
  font-size: 14px;
  line-height: 1.6;
}

.coke-site .customer-friend-link-box {
  display: grid;
  gap: 12px;
}

.coke-site .customer-friend-link-box code {
  display: block;
  overflow-wrap: anywhere;
  padding: 14px;
  border-radius: 16px;
  background: rgba(27, 20, 16, 0.06);
  color: var(--ink-900);
  font-size: 13px;
}

.coke-site .customer-friends-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.coke-site .customer-friends-list {
  display: grid;
  gap: 10px;
}

.coke-site .customer-friend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(27, 20, 16, 0.06);
}

.coke-site .customer-friend-row strong,
.coke-site .customer-friend-row span {
  display: block;
}

.coke-site .customer-friend-row strong {
  color: var(--ink-1000);
  font-size: 15px;
}

.coke-site .customer-friend-row span,
.coke-site .customer-friends-empty {
  color: var(--ink-700);
  font-size: 13px;
}

.coke-site .customer-friend-row button {
  border: 1px solid rgba(27, 20, 16, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--ink-900);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  padding: 8px 12px;
}

.coke-site .customer-friend-row__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 760px) {
  .coke-site .customer-friends-grid,
  .coke-site .customer-friend-row {
    grid-template-columns: 1fr;
  }

  .coke-site .customer-friend-row {
    align-items: stretch;
    flex-direction: column;
  }

  .coke-site .customer-friend-row__actions {
    justify-content: flex-start;
  }
}
```

- [ ] **Step 5: Run the page test to verify it passes**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/account/friends/page.test.tsx'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gateway/packages/web/app/'(customer)'/account/friends/page.tsx gateway/packages/web/app/'(customer)'/account/friends/page.test.tsx gateway/packages/web/app/public-site.css
git commit -m "feat: add customer friend management page"
```

### Task 4: Final Verification

**Files:**
- No new files unless a previous task reveals a necessary small fix.

- [ ] **Step 1: Run the focused web test set**

Run:

```bash
pnpm --dir gateway/packages/web test -- lib/customer-friends.test.ts 'app/(customer)/account/layout.test.tsx' lib/i18n.test.ts 'app/(customer)/account/friends/page.test.tsx'
```

Expected: PASS.

- [ ] **Step 2: Run diff-aware repo verification suggestions**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~3
zsh scripts/review-trigger --base HEAD~3
```

Expected: commands complete. Record the suggested surfaces and whether review-trigger asks for human review.

- [ ] **Step 3: Run the suggested lightweight surface if applicable**

For frontend-only changes, if `scripts/suggest-verification` points at a gateway/web or repo-os-docs surface, run that exact suggested command. If the suggestion is too broad or blocked by environment, record the exact blocker.

- [ ] **Step 4: Inspect final git status**

Run:

```bash
git status --short
```

Expected: only pre-existing unrelated working-tree changes remain, or a clean tree if those changes were already handled outside this plan.

- [ ] **Step 5: Commit verification-only fixes if needed**

If a small bug is found during verification, fix it with TDD when possible, rerun the failing command, and commit:

```bash
git add <changed-files>
git commit -m "fix: polish friend management page"
```

Do not commit unrelated pre-existing files.

## Self-Review

- Spec coverage: The plan covers `/account/friends`, navigation, friend-link controls, incoming/outgoing requests, current friends, auth redirection, i18n copy, focused tests, and final verification.
- Backend scope: The plan reuses existing Gateway scheduling endpoints and does not change backend models or routes.
- Placeholder scan: No placeholder markers or unspecified implementation steps are left.
- Type consistency: The wrapper types match `customer-scheduling-routes.ts` DTOs: friend requests include `direction` and `counterpartAccountId`; friends include `counterpartProfile` when available.
