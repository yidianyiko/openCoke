export type Locale = 'en' | 'zh';

export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_STORAGE_KEY = 'coke-locale';
export const LOCALE_COOKIE_NAME = 'coke-locale';
const LOCALE_BOOTSTRAP_KEY = '__COKE_LOCALE__';

type SharedButtonMessages = {
  signIn: string;
  register: string;
};

type BindWechatViewModelMessages = {
  missing: {
    eyebrow: string;
    title: string;
    description: string;
    primaryActionLabel: string;
  };
  disconnected: {
    eyebrow: string;
    title: string;
    description: string;
    primaryActionLabel: string;
  };
  pending: {
    eyebrow: string;
    title: string;
    description: string;
    primaryActionLabel: string;
  };
  connected: {
    eyebrow: string;
    title: string;
    descriptionWithIdentity: string;
    descriptionWithoutIdentity: string;
    primaryActionLabel: string;
  };
  error: {
    eyebrow: string;
    title: string;
    descriptionFallback: string;
    primaryActionLabel: string;
    secondaryActionLabel: string;
  };
  archived: {
    eyebrow: string;
    title: string;
    description: string;
    primaryActionLabel: string;
  };
};

type CustomerLayoutMessages = {
  brandName: string;
  brandTagline: string;
  navLabel: string;
  eyebrow: string;
  title: string;
  body: string;
  secondaryBody: string;
  trustLines: string[];
};

type CokeUserLayoutMessages = CustomerLayoutMessages;

type CustomerPagesMessages = {
  login: {
    eyebrow: string;
    heroTitle: string;
    heroBody: string;
    heroSecondaryBody: string;
    backToHomepage: string;
    title: string;
    description: string;
    emailLabel: string;
    emailPlaceholder: string;
    passwordLabel: string;
    passwordPlaceholder: string;
    submit: string;
    submitting: string;
    forgotPasswordPrompt: string;
    forgotPasswordLink: string;
    registerPrompt: string;
    registerLink: string;
    suspendedError: string;
    emailVerificationRequired: string;
    subscriptionRenewalRequired: string;
    success: string;
    genericError: string;
    verificationRecoveryTitle: string;
    verificationRecoveryDescription: string;
    verificationRetryDescription: string;
    resendVerificationEmail: string;
    resendingVerificationEmail: string;
    resendVerificationSuccess: string;
    resendVerificationError: string;
  };
  register: {
    eyebrow: string;
    heroTitle: string;
    heroBody: string;
    heroSecondaryBody: string;
    backToHomepage: string;
    title: string;
    description: string;
    displayNameLabel: string;
    displayNamePlaceholder: string;
    emailLabel: string;
    emailPlaceholder: string;
    passwordLabel: string;
    passwordPlaceholder: string;
    submit: string;
    submitting: string;
    signInPrompt: string;
    signInLink: string;
    emailAlreadyExistsError: string;
    genericError: string;
  };
  forgotPassword: {
    title: string;
    description: string;
    emailLabel: string;
    emailPlaceholder: string;
    submit: string;
    submitting: string;
    success: string;
    backToSignInPrompt: string;
    backToSignInLink: string;
    genericError: string;
  };
  resetPassword: {
    title: string;
    description: string;
    tokenLabel: string;
    tokenPlaceholder: string;
    passwordLabel: string;
    confirmPasswordLabel: string;
    submit: string;
    submitting: string;
    mismatchError: string;
    success: string;
    requestNewLinkPrompt: string;
    requestNewLinkLink: string;
    genericError: string;
  };
  verifyEmail: {
    title: string;
    description: string;
    verifyingDescription: string;
  };
  claim: {
    eyebrow: string;
    title: string;
    description: string;
    tokenLabel: string;
    tokenPlaceholder: string;
    passwordLabel: string;
    confirmPasswordLabel: string;
    submit: string;
    submitting: string;
    mismatchError: string;
    invalidOrExpiredError: string;
    emailAlreadyExistsError: string;
    genericError: string;
    signInPrompt: string;
    signInLink: string;
  };
  claimEntry: {
    eyebrow: string;
    title: string;
    description: string;
    emailLabel: string;
    emailPlaceholder: string;
    submit: string;
    submitting: string;
    success: string;
    invalidOrExpiredError: string;
    emailAlreadyExistsError: string;
    genericError: string;
    signInPrompt: string;
    signInLink: string;
  };
  channelsIndex: {
    eyebrow: string;
    title: string;
    description: string;
    wechatPersonalTitle: string;
    wechatPersonalDescription: string;
  };
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
    inviteTitle: string;
    inviteDescription: string;
    inviteTargetLabel: string;
    inviteSend: string;
    inviteSending: string;
    inviteSent: string;
    inviteAlreadyFriend: string;
    inviteLoadFailure: string;
    inviteUnavailable: string;
    friendsTitle: string;
    emptyFriends: string;
    loading: string;
    loadFailure: string;
    actionFailure: string;
    removeFriend: string;
    unknownFriend: string;
  };
  myAgent: {
    eyebrow: string;
    title: string;
    description: string;
    configured: string;
    loadFailure: string;
    saveFailure: string;
    resetFailure: string;
    saved: string;
    reset: string;
    save: string;
    saving: string;
    basicIdentity: string;
    agentProfile: string;
    proactiveMessages: string;
    memoryPersonalization: string;
  };
  bindWechat: {
    blocked: {
      accessEyebrow: string;
      suspendedTitle: string;
      suspendedDescription: string;
      prerequisitesTitle: string;
      prerequisitesDescription: string;
      verifyEmail: string;
      renewSubscription: string;
    };
    loadFailure: {
      title: string;
    };
    loading: {
      title: string;
      description: string;
    };
    statusDescriptions: {
      missing: string;
      archived: string;
      disconnected: string;
    };
    pairing: {
      codeLabel: string;
      instructions: string;
      preparing: string;
      expiresPrefix: string;
      activeSuffix: string;
    };
    connectedCard: {
      eyebrow: string;
      descriptionWithIdentity: string;
      descriptionWithoutIdentity: string;
      accountOwnershipSuffix: string;
    };
    errorCard: {
      eyebrow: string;
      fallbackDescription: string;
    };
    nextSteps: {
      title: string;
      missing: string;
      disconnected: string;
      pending: string;
      connected: string;
      error: string;
      archived: string;
    };
    busyActions: {
      create: string;
      connect: string;
      refresh: string;
      disconnect: string;
      reconnect: string;
      archive: string;
    };
    accountPrompt: string;
    createAccount: string;
    viewModel: BindWechatViewModelMessages;
  };
};

type CokeUserPagesMessages = {
  renew: {
    title: string;
    preparing: string;
    ready: string;
    signIn: string;
    backToSetup: string;
    genericError: string;
  };
  paymentSuccess: {
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
  paymentCancel: {
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
};

export type LocaleMessages = {
  common: {
    languageLabel: string;
    localeLabel: string;
    retryLabel: string;
    signOutLabel: string;
  };
  publicShell: {
    brandTagline: string;
    nav: Array<{ href: string; label: string }>;
    cta: SharedButtonMessages;
    languageSwitchLabel: string;
  };
  homepage: {
    hero: {
      eyebrow: string;
      title: string;
      subtitle: string;
      titleLine1: string;
      titleItalicMiddle: string;
      titleLine3: string;
      body: string;
      primaryCta: string;
      secondaryCta: string;
      foot: string;
    };
    stats: Array<{ value: string; label: string }>;
    spotlight: {
      title: string;
      body: string;
    };
    platforms: {
      eyebrow: string;
      title: string;
      subtitle: string;
      items: string[];
    };
    features: {
      eyebrow: string;
      title: string;
      subtitle: string;
      items: Array<{
        title: string;
        subtitle: string;
        body: string;
      }>;
    };
    architecture: {
      eyebrow: string;
      title: string;
      subtitle: string;
      points: string[];
    };
    contact: {
      eyebrow: string;
      title: string;
      body: string;
      primaryCta: string;
      secondaryCta: string;
      placeholder: string;
      note: string;
      thanks: string;
    };
    footer: {
      productHeading: string;
      accountHeading: string;
      companyHeading: string;
      copyright: string;
      tagline: string;
      productLinks: string[];
      accountLinks: string[];
      companyLinks: string[];
    };
  };
  customerLayout: CustomerLayoutMessages;
  cokeUserLayout: CokeUserLayoutMessages;
  customerPages: CustomerPagesMessages;
  cokeUserPages: CokeUserPagesMessages;
};

type MessagesCatalog = Record<Locale, LocaleMessages>;

export const messages: MessagesCatalog = {
  en: {
    common: {
      languageLabel: 'Language',
      localeLabel: 'Locale',
      retryLabel: 'Retry',
      signOutLabel: 'Sign out',
    },
    publicShell: {
      brandTagline: 'An AI Partner That Grows With You',
      nav: [
        { href: '/#capabilities', label: 'Capabilities' },
        { href: '/#scenarios', label: 'Scenarios' },
        { href: '/demos', label: 'Demos' },
        { href: '/#voices', label: 'Proof' },
        { href: '/#download', label: 'Start' },
      ],
      cta: {
        signIn: 'Sign in',
        register: 'Register',
      },
      languageSwitchLabel: 'Switch language',
    },
    homepage: {
      hero: {
        eyebrow: 'Supervision That Follows Up',
        title: 'An AI supervisor that follows up until it is done',
        subtitle: 'An AI Supervisor That Follows Up Until It Is Done',
        titleLine1: 'An AI supervisor',
        titleItalicMiddle: 'that follows up',
        titleLine3: 'until it is done.',
        body: 'Kap AI turns goals into reminders, check-ins, and follow-up across personal WeChat and WhatsApp, with Google Calendar import for schedule-driven reminders.',
        primaryCta: 'Register',
        secondaryCta: 'Sign in',
        foot: 'Personal WeChat · WhatsApp · Google Calendar · Reminders',
      },
      stats: [
        { value: 'WeChat', label: 'Personal channel' },
        { value: 'WhatsApp', label: 'Global entry' },
        { value: 'Calendar', label: 'Imported reminders' },
        { value: 'Follow-up', label: 'Deferred actions' },
      ],
      spotlight: {
        title: 'One assistant, all platforms',
        body: 'No context switching. Kap AI meets you inside the channels you already rely on.',
      },
      platforms: {
        eyebrow: 'Platforms',
        title: 'Seamlessly integrated across major IM platforms',
        subtitle:
          'Kap AI fits into the channels you already use instead of asking you to learn a new one.',
        items: ['WeChat', 'Telegram', 'DingTalk', 'Lark', 'Slack', 'Discord'],
      },
      features: {
        eyebrow: 'Features',
        title: 'Powerful assistance for modern work and life',
        subtitle:
          'From planning to proactive follow-through, Kap AI stays involved instead of answering once and disappearing.',
        items: [
          {
            title: 'Scheduling',
            subtitle: 'Planning',
            body: 'Understands context and helps you arrange meetings, reminders, and day-to-day follow-ups.',
          },
          {
            title: 'Task planning',
            subtitle: 'Roadmaps',
            body: 'Breaks complex goals into clearer action paths that adapt to the way you actually work.',
          },
          {
            title: 'Data analysis',
            subtitle: 'Insights',
            body: 'Finds patterns in your rhythm and behavior, then turns them into practical next steps.',
          },
          {
            title: 'Proactive workflows',
            subtitle: 'Automation',
            body: 'Steps in at the right moment to remind, nudge, and move work forward without constant prompting.',
          },
        ],
      },
      architecture: {
        eyebrow: 'Architecture',
        title: 'Built on a reliable technical foundation',
        subtitle:
          'The public experience and the long-running product both depend on a stable core, not just a polished landing page.',
        points: [
          'Modular architecture',
          'AI-driven orchestration',
          'Reliable data persistence',
          'Privacy-first operation',
        ],
      },
      contact: {
        eyebrow: 'Start',
        title: 'Create your account, then connect the channel you use.',
        body: 'Register, verify your email, and continue into personal WeChat setup. Global users can start directly from the WhatsApp entry.',
        primaryCta: 'Create account',
        secondaryCta: 'Existing account',
        placeholder: 'your email',
        note: "We won't share your email with anyone else.",
        thanks: "Thanks. We'll be in touch within 24 hours.",
      },
      footer: {
        productHeading: 'Product',
        accountHeading: 'Account',
        companyHeading: 'Company',
        copyright: '© 2026 Kap AI',
        tagline: 'Built to keep goals moving.',
        productLinks: ['Capabilities', 'Scenarios', 'Demos', 'FAQ'],
        accountLinks: ['Sign in', 'Register', 'WeChat setup', 'Renew'],
        companyLinks: ['About', 'Terms', 'Privacy'],
      },
    },
    customerLayout: {
      brandName: 'Kap AI',
      brandTagline: 'Keep your next Kap step moving',
      navLabel: 'Access, verification, and WeChat setup',
      eyebrow: 'Continue with Kap',
      title: 'Finish the next step in one place',
      body: 'Sign in, register, verify your email, and reconnect your personal WeChat flow without leaving the same product.',
      secondaryBody: 'When you come back, Kap should make the next required action obvious.',
      trustLines: [
        'End-to-end encrypted transport',
        'Return straight to the next step',
        'Connection status stays visible',
      ],
    },
    cokeUserLayout: {
      brandName: 'Kap AI',
      brandTagline: 'Subscription and Kap business management',
      navLabel: 'Manage Kap billing and delivery state',
      eyebrow: 'Kap Workspace',
      title: 'Keep your Kap service active',
      body: 'Handle renewal, payment follow-up, and the business-side steps that still stay under Kap-specific routes.',
      secondaryBody: 'Generic sign-in, recovery, and customer channel setup now live under the neutral customer routes.',
      trustLines: [
        'Billing and delivery state stay visible in one place',
        'Renewal and payment follow-up remain on Kap routes',
        'Account access and channel setup stay separated by design',
      ],
    },
    customerPages: {
      login: {
        eyebrow: 'Sign in',
        heroTitle: 'Return to your Kap account',
        heroBody:
          'After sign-in, Kap keeps the existing verification and subscription checks, then routes you back to your personal WeChat setup.',
        heroSecondaryBody:
          'Use the same account flow you started from the public homepage.',
        backToHomepage: 'Back to homepage',
        title: 'Sign in to Kap',
        description: 'Enter your email and password to continue your personal Kap flow.',
        emailLabel: 'Email',
        emailPlaceholder: 'alice@example.com',
        passwordLabel: 'Password',
        passwordPlaceholder: 'Enter your password',
        submit: 'Sign in to Kap',
        submitting: 'Signing in...',
        forgotPasswordPrompt: 'Forgot your password?',
        forgotPasswordLink: 'Reset it',
        registerPrompt: 'Need an account?',
        registerLink: 'Create one',
        suspendedError: 'Your Kap account is suspended.',
        emailVerificationRequired: 'Email verification is required.',
        subscriptionRenewalRequired: 'Subscription renewal is required.',
        success: 'Sign-in succeeded.',
        genericError: 'Unable to sign in right now.',
        verificationRecoveryTitle: 'Verify your email',
        verificationRecoveryDescription:
          'This link is invalid or expired. Resend a verification email to continue.',
        verificationRetryDescription:
          "We couldn't verify your email right now. Resend a verification email to continue.",
        resendVerificationEmail: 'Resend verification email',
        resendingVerificationEmail: 'Sending verification email...',
        resendVerificationSuccess:
          "Verification email sent. Check your inbox. The link is valid for 15 minutes. If you don't see it, check your spam folder.",
        resendVerificationError: 'Unable to resend the verification email right now.',
      },
      register: {
        eyebrow: 'Register',
        heroTitle: 'Create your Kap account',
        heroBody:
          'Registration leads into email verification first, then the personal WeChat channel setup you already use.',
        heroSecondaryBody: 'Create your account once and continue the rest of the setup from here.',
        backToHomepage: 'Back to homepage',
        title: 'Create your Kap account',
        description: 'Register here, verify your email, and continue into personal channel setup.',
        displayNameLabel: 'Display name',
        displayNamePlaceholder: 'Alice',
        emailLabel: 'Email',
        emailPlaceholder: 'alice@example.com',
        passwordLabel: 'Password',
        passwordPlaceholder: 'Create a password',
        submit: 'Create Kap account',
        submitting: 'Creating account...',
        signInPrompt: 'Already registered?',
        signInLink: 'Sign in',
        emailAlreadyExistsError: 'That email address is already in use. Sign in or use a different email.',
        genericError: 'Unable to create your account right now.',
      },
      forgotPassword: {
        title: 'Forgot your password',
        description:
          'Enter your account email and we will send a reset link if the address is registered.',
        emailLabel: 'Email',
        emailPlaceholder: 'alice@example.com',
        submit: 'Send reset link',
        submitting: 'Sending...',
        success: 'Password reset instructions were sent if the account exists.',
        backToSignInPrompt: 'Remembered your password?',
        backToSignInLink: 'Back to sign in',
        genericError: 'Unable to send password reset instructions right now.',
      },
      resetPassword: {
        title: 'Reset your password',
        description: 'Paste the reset token from your email and choose a new password.',
        tokenLabel: 'Reset token',
        tokenPlaceholder: 'Paste the token from your email',
        passwordLabel: 'New password',
        confirmPasswordLabel: 'Confirm password',
        submit: 'Reset password',
        submitting: 'Saving...',
        mismatchError: 'Passwords do not match.',
        success: 'Password reset complete.',
        requestNewLinkPrompt: 'Need to start over?',
        requestNewLinkLink: 'Request a new reset link',
        genericError: 'Unable to reset your password right now.',
      },
      verifyEmail: {
        title: 'Verify your email',
        description: 'We are preparing your secure email verification.',
        verifyingDescription: 'Verifying your email link now...',
      },
      claim: {
        eyebrow: 'Shared channel access',
        title: 'Claim your customer account',
        description: 'Set a password to activate the account that was pre-provisioned from your first inbound message.',
        tokenLabel: 'Claim token',
        tokenPlaceholder: 'Paste the claim token from your email',
        passwordLabel: 'New password',
        confirmPasswordLabel: 'Confirm password',
        submit: 'Activate account',
        submitting: 'Activating...',
        mismatchError: 'Passwords do not match.',
        invalidOrExpiredError: 'This claim link is invalid or has expired.',
        emailAlreadyExistsError: 'That email address is already in use. Sign in or request a new claim link with a different email.',
        genericError: 'Unable to claim your account right now.',
        signInPrompt: 'Already claimed your account?',
        signInLink: 'Sign in',
      },
      claimEntry: {
        eyebrow: 'Shared channel access',
        title: 'Claim your customer account',
        description: 'Enter your email first and we will send a secure claim link so you can continue to calendar import.',
        emailLabel: 'Email',
        emailPlaceholder: 'alice@example.com',
        submit: 'Email me a claim link',
        submitting: 'Sending...',
        success: 'Check your inbox for the claim link.',
        invalidOrExpiredError:
          'This WhatsApp claim link is invalid or has expired. Request a fresh link from WhatsApp to continue.',
        emailAlreadyExistsError:
          'That email address is already in use. Sign in or request a new claim link with a different email.',
        genericError: 'Unable to send your claim email right now.',
        signInPrompt: 'Already claimed your account?',
        signInLink: 'Sign in',
      },
      channelsIndex: {
        eyebrow: 'Phase 1 channels',
        title: 'Customer channels',
        description: 'Manage the customer channel surfaces that are available in the neutral ClawScale shell today.',
        wechatPersonalTitle: 'Personal WeChat',
        wechatPersonalDescription: 'Connect, reconnect, or archive your personal WeChat channel.',
      },
      friends: {
        eyebrow: 'Friends',
        title: 'Friend management',
        description: 'Share your add-friend link and manage current friends.',
        linkTitle: 'My friend link',
        linkDescription: 'Share this URL with someone who should be able to add you as a friend.',
        copyLink: 'Copy link',
        copied: 'Link copied.',
        resetLink: 'Reset link',
        disableLink: 'Disable current link',
        linkDisabled: 'The current link was disabled. A new link can be created when you refresh this page.',
        inviteTitle: 'Add friend',
        inviteDescription: 'Confirm this link from your account to add this person as a friend.',
        inviteTargetLabel: 'Target account',
        inviteSend: 'Add friend',
        inviteSending: 'Adding...',
        inviteSent: 'Friend added.',
        inviteAlreadyFriend: 'This account is already in your friends list.',
        inviteLoadFailure: 'Unable to load this friend link right now.',
        inviteUnavailable: 'This invitation can no longer add a friend.',
        friendsTitle: 'Current friends',
        emptyFriends: 'No friends yet.',
        loading: 'Loading friend data...',
        loadFailure: 'Unable to load friend data right now.',
        actionFailure: 'Unable to update friend data right now.',
        removeFriend: 'Remove friend',
        unknownFriend: 'Unknown account',
      },
      myAgent: {
        eyebrow: 'Agent settings',
        title: 'My Agent',
        description: 'Customize the visible identity and profile Kap uses with you.',
        configured: 'configured',
        loadFailure: 'Unable to load agent settings right now.',
        saveFailure: 'Unable to save agent settings right now.',
        resetFailure: 'Unable to reset agent settings right now.',
        saved: 'Agent settings saved.',
        reset: 'Reset',
        save: 'Save',
        saving: 'Saving...',
        basicIdentity: 'Basic identity',
        agentProfile: 'Agent profile',
        proactiveMessages: 'Proactive messages',
        memoryPersonalization: 'Memory and personalization',
      },
      bindWechat: {
        blocked: {
          accessEyebrow: 'Account access',
          suspendedTitle: 'Your Kap account is suspended',
          suspendedDescription:
            'Contact support to restore access before binding a personal WeChat channel.',
          prerequisitesTitle:
            'Verify your email and renew your subscription before creating a WeChat channel.',
          prerequisitesDescription:
            'Finish the required account steps, then come back here to create or reconnect your channel.',
          verifyEmail: 'Verify email',
          renewSubscription: 'Renew subscription',
        },
        loadFailure: {
          title: 'Unable to load your WeChat channel',
        },
        loading: {
          title: 'Loading your WeChat channel',
          description: 'We are checking the personal channel attached to this Kap account.',
        },
        statusDescriptions: {
          missing: 'Create the channel first, then send a pairing code from your own WeChat.',
          archived: 'Archived channels do not route messages. Create a fresh channel to start over.',
          disconnected:
            'The channel exists but is not connected yet. Send a pairing code to bring it online.',
        },
        pairing: {
          codeLabel: 'Pairing code',
          instructions: 'Add the Coke WeChat bot and send this code.',
          preparing: 'Preparing your pairing code...',
          expiresPrefix: 'This pairing code expires at',
          activeSuffix: 'The current pairing code is still active.',
        },
        connectedCard: {
          eyebrow: 'Connected',
          descriptionWithIdentity: 'WeChat {identity} is connected to this Kap account.',
          descriptionWithoutIdentity: 'Your personal WeChat channel is connected and ready.',
          accountOwnershipSuffix: '{name}, this belongs to your Kap account.',
        },
        errorCard: {
          eyebrow: 'Connection error',
          fallbackDescription: 'The last connect attempt failed. Retry or archive this channel.',
        },
        nextSteps: {
          title: 'What you can do next',
          missing: 'Create your personal WeChat channel for this account.',
          disconnected: 'Send a pairing code to connect the existing channel.',
          pending:
            'Add the Coke WeChat bot, send the pairing code, then continue messaging from that WeChat account.',
          connected: 'Disconnect the channel when you want to take it offline.',
          error: 'Retry the connect flow or archive the broken channel.',
          archived: 'Create a fresh channel if you want to start over.',
        },
        busyActions: {
          create: 'Creating...',
          connect: 'Connecting...',
          refresh: 'Refreshing...',
          disconnect: 'Disconnecting...',
          reconnect: 'Reconnecting...',
          archive: 'Archiving...',
        },
        accountPrompt: 'Need an account?',
        createAccount: 'Create one',
        viewModel: {
          missing: {
            eyebrow: 'No channel yet',
            title: 'Create my WeChat channel',
            description:
              'Create a personal WeChat channel for this Kap account, then bind it with a pairing code.',
            primaryActionLabel: 'Create my WeChat channel',
          },
          disconnected: {
            eyebrow: 'Channel created',
            title: 'Connect WeChat',
            description:
              'Your personal WeChat channel exists. Send the pairing code to bring it online.',
            primaryActionLabel: 'Connect WeChat',
          },
          pending: {
            eyebrow: 'Pairing in progress',
            title: 'Send the pairing code to connect',
            description: 'Use the code below to bind your WeChat account to Kap.',
            primaryActionLabel: 'Refresh code',
          },
          connected: {
            eyebrow: 'Connected',
            title: 'WeChat is connected',
            descriptionWithIdentity: 'Your personal channel is live as {identity}.',
            descriptionWithoutIdentity: 'Your personal WeChat channel is connected and ready.',
            primaryActionLabel: 'Disconnect WeChat',
          },
          error: {
            eyebrow: 'Connection error',
            title: 'Reconnect or archive your channel',
            descriptionFallback:
              'The last connect attempt failed. You can retry or archive this channel.',
            primaryActionLabel: 'Reconnect',
            secondaryActionLabel: 'Archive channel',
          },
          archived: {
            eyebrow: 'Archived',
            title: 'This WeChat channel is archived',
            description: 'Create a fresh personal channel if you want to use WeChat again.',
            primaryActionLabel: 'Create my WeChat channel again',
          },
        },
      },
    },
    cokeUserPages: {
      renew: {
        title: 'Renew your access',
        preparing: 'Preparing your renewal checkout...',
        ready: 'Return to checkout when you are ready.',
        signIn: 'Sign in',
        backToSetup: 'Back to setup',
        genericError: 'Unable to start renewal right now.',
      },
      paymentSuccess: {
        title: 'Payment complete',
        description:
          'Your renewal payment was received. Return to your account to finish connecting WeChat.',
        primaryCta: 'Go to WeChat setup',
        secondaryCta: 'Check renewal',
      },
      paymentCancel: {
        title: 'Payment canceled',
        description:
          'The checkout flow was canceled before payment completed. You can try again when you are ready.',
        primaryCta: 'Restart renewal',
        secondaryCta: 'Back to setup',
      },
    },
  },
  zh: {
    common: {
      languageLabel: '语言',
      localeLabel: '区域',
      retryLabel: '重试',
      signOutLabel: '退出登录',
    },
    publicShell: {
      brandTagline: '与您共同成长的 AI 助手',
      nav: [
        { href: '/#capabilities', label: '能力' },
        { href: '/#scenarios', label: '场景' },
        { href: '/demos', label: '示例' },
        { href: '/#voices', label: '口碑' },
        { href: '/#download', label: '开始' },
      ],
      cta: {
        signIn: '登录',
        register: '注册',
      },
      languageSwitchLabel: '切换语言',
    },
    homepage: {
      hero: {
        eyebrow: '会主动跟进的监督',
        title: '会主动跟进直到完成的 AI 监督者',
        subtitle: '会主动跟进的 AI 监督者',
        titleLine1: '会主动跟进',
        titleItalicMiddle: '直到完成的',
        titleLine3: 'AI 监督者。',
        body: 'Kap AI 会把目标变成提醒、检查和后续跟进，通过个人微信或 WhatsApp 触达你，也可以把 Google Calendar 导入成提醒。',
        primaryCta: '注册',
        secondaryCta: '登录',
        foot: '个人微信 · WhatsApp · Google Calendar · 提醒',
      },
      stats: [
        { value: '微信', label: '个人通道' },
        { value: 'WhatsApp', label: '全球入口' },
        { value: '日历', label: '导入提醒' },
        { value: '跟进', label: '延迟动作' },
      ],
      spotlight: {
        title: '一个助手，全平台覆盖',
        body: '无需在应用之间切换，Kap AI 会出现在你已经在使用的平台里。',
      },
      platforms: {
        eyebrow: '平台',
        title: '自然融入主流即时通讯平台',
        subtitle: 'Kap AI 会进入你已经习惯的沟通渠道，而不是要求你重新学习一个新入口。',
        items: ['WeChat', 'Telegram', 'DingTalk', 'Lark', 'Slack', 'Discord'],
      },
      features: {
        eyebrow: '功能',
        title: '面向现代工作与生活的高效协助',
        subtitle: '从规划到主动推进，Kap AI 会持续参与，而不是只回答一次就离开。',
        items: [
          {
            title: '日程管理',
            subtitle: '规划',
            body: '智能理解上下文，帮助你安排会议、提醒和日常跟进。',
          },
          {
            title: '任务规划',
            subtitle: '路径',
            body: '把复杂目标拆成更清晰的行动路径，并随着使用不断贴近你的习惯。',
          },
          {
            title: '数据分析',
            subtitle: '洞察',
            body: '从你的节奏和行为里总结模式，给出可执行的下一步建议。',
          },
          {
            title: '主动工作流',
            subtitle: '自动化',
            body: '在合适的时间主动提醒、推进事项，而不是等你每次都来询问。',
          },
        ],
      },
      architecture: {
        eyebrow: '架构',
        title: '建立在可靠的技术基础之上',
        subtitle: '公开体验和长期运行都需要稳定的底层，而不只是一个漂亮首页。',
        points: ['模块化架构', '智能编排', '稳定数据持久化', '隐私优先运作'],
      },
      contact: {
        eyebrow: '开始',
        title: '创建账号，然后连接你真正使用的通道。',
        body: '先注册、验证邮箱，再继续进入个人微信设置。海外用户可以直接从 WhatsApp 入口开始。',
        primaryCta: '创建账号',
        secondaryCta: '已有账号',
        placeholder: '你的邮箱',
        note: '我们不会把你的邮箱分享给第三方。',
        thanks: '谢谢。我们会在 24 小时内联系你。',
      },
      footer: {
        productHeading: '产品',
        accountHeading: '账号',
        companyHeading: '公司',
        copyright: '© 2026 Kap AI',
        tagline: '让目标继续往前走。',
        productLinks: ['能力', '场景', '示例', '常见问题'],
        accountLinks: ['登录', '注册', '微信设置', '续费'],
        companyLinks: ['关于', '条款', '隐私'],
      },
    },
    customerLayout: {
      brandName: 'Kap AI',
      brandTagline: '把你的下一步继续推进',
      navLabel: '账号访问、验证与微信连接',
      eyebrow: '继续使用 Kap',
      title: '在同一个地方完成下一步',
      body: '登录、注册、邮箱验证和个人微信连接都在这里继续，不需要离开同一套产品界面。',
      secondaryBody: '回来之后，你应该一眼就知道下一步该做什么。',
      trustLines: [
        '全程加密传输',
        '回来就能继续下一步',
        '连接状态持续可见',
      ],
    },
    cokeUserLayout: {
      brandName: 'Kap AI',
      brandTagline: '管理订阅与 Kap 业务状态',
      navLabel: '管理 Kap 账单与交付状态',
      eyebrow: 'Kap 工作区',
      title: '保持你的 Kap 服务处于启用状态',
      body: '在这里处理续费、支付后续动作，以及仍然保留在 Kap 专属路由下的业务步骤。',
      secondaryBody: '通用登录、找回访问和客户通道设置现在都放在中立的 customer 路由下。',
      trustLines: [
        '账单与交付状态集中展示',
        '续费与支付后续动作仍保留在 Kap 路由下',
        '账号访问与通道设置按职责分离',
      ],
    },
    customerPages: {
      login: {
        eyebrow: '登录',
        heroTitle: '返回你的 Kap 账号',
        heroBody: '登录后，系统会继续检查邮箱验证和订阅状态，再把你带回个人微信设置流程。',
        heroSecondaryBody: '使用你在官网入口创建的同一个账号继续后续流程。',
        backToHomepage: '返回首页',
        title: '登录 Kap',
        description: '输入邮箱和密码，继续你的个人 Kap 使用流程。',
        emailLabel: '邮箱',
        emailPlaceholder: 'alice@example.com',
        passwordLabel: '密码',
        passwordPlaceholder: '输入你的密码',
        submit: '登录 Kap',
        submitting: '登录中...',
        forgotPasswordPrompt: '忘记密码？',
        forgotPasswordLink: '立即重置',
        registerPrompt: '还没有账号？',
        registerLink: '创建账号',
        suspendedError: '你的 Kap 账号已被停用。',
        emailVerificationRequired: '需要先完成邮箱验证。',
        subscriptionRenewalRequired: '需要先完成订阅续费。',
        success: '登录成功。',
        genericError: '暂时无法登录，请稍后再试。',
        verificationRecoveryTitle: '验证你的邮箱',
        verificationRecoveryDescription: '这个链接已失效或已过期。请重新发送验证邮件继续。',
        verificationRetryDescription: '暂时无法验证你的邮箱。请重新发送验证邮件继续。',
        resendVerificationEmail: '重新发送验证邮件',
        resendingVerificationEmail: '正在发送验证邮件...',
        resendVerificationSuccess: '验证邮件已发送，请查收邮箱。链接 15 分钟内有效；如果没有看到，请检查垃圾邮箱。',
        resendVerificationError: '暂时无法重新发送验证邮件，请稍后再试。',
      },
      register: {
        eyebrow: '注册',
        heroTitle: '创建你的 Kap 账号',
        heroBody: '注册完成后会先进入邮箱验证，然后继续进入你已经在使用的个人微信设置流程。',
        heroSecondaryBody: '先完成账号创建，再从这里继续后续步骤。',
        backToHomepage: '返回首页',
        title: '创建你的 Kap 账号',
        description: '在这里注册账号、完成邮箱验证，然后继续进入个人通道设置。',
        displayNameLabel: '昵称',
        displayNamePlaceholder: '例如：小可',
        emailLabel: '邮箱',
        emailPlaceholder: 'alice@example.com',
        passwordLabel: '密码',
        passwordPlaceholder: '创建一个密码',
        submit: '创建 Kap 账号',
        submitting: '账号创建中...',
        signInPrompt: '已经注册？',
        signInLink: '去登录',
        emailAlreadyExistsError: '该邮箱地址已被占用。请直接登录，或使用其他邮箱注册。',
        genericError: '暂时无法创建账号，请稍后再试。',
      },
      forgotPassword: {
        title: '忘记密码',
        description: '输入账号邮箱，如果该地址已注册，我们会发送重置链接。',
        emailLabel: '邮箱',
        emailPlaceholder: 'alice@example.com',
        submit: '发送重置链接',
        submitting: '发送中...',
        success: '如果该账号存在，我们已经发送了密码重置说明。',
        backToSignInPrompt: '想起密码了？',
        backToSignInLink: '返回登录',
        genericError: '暂时无法发送重置说明，请稍后再试。',
      },
      resetPassword: {
        title: '重置密码',
        description: '粘贴邮件中的重置令牌，并设置一个新密码。',
        tokenLabel: '重置令牌',
        tokenPlaceholder: '粘贴邮件中的令牌',
        passwordLabel: '新密码',
        confirmPasswordLabel: '确认密码',
        submit: '重置密码',
        submitting: '保存中...',
        mismatchError: '两次输入的密码不一致。',
        success: '密码重置完成。',
        requestNewLinkPrompt: '需要重新开始？',
        requestNewLinkLink: '申请新的重置链接',
        genericError: '暂时无法重置密码，请稍后再试。',
      },
      verifyEmail: {
        title: '验证邮箱',
        description: '我们正在为你准备安全的邮箱验证。',
        verifyingDescription: '正在验证你的邮箱链接...',
      },
      claim: {
        eyebrow: '共享通道访问',
        title: '认领你的客户账号',
        description: '为首次入站消息自动预建的账号设置密码，完成激活。',
        tokenLabel: '认领令牌',
        tokenPlaceholder: '粘贴邮件中的认领令牌',
        passwordLabel: '新密码',
        confirmPasswordLabel: '确认密码',
        submit: '激活账号',
        submitting: '正在激活...',
        mismatchError: '两次输入的密码不一致。',
        invalidOrExpiredError: '这个认领链接无效或已过期。',
        emailAlreadyExistsError: '该邮箱地址已被占用。请直接登录，或使用其他邮箱重新申请认领链接。',
        genericError: '暂时无法认领你的账号，请稍后再试。',
        signInPrompt: '已经认领过账号？',
        signInLink: '去登录',
      },
      claimEntry: {
        eyebrow: '共享通道访问',
        title: '认领你的客户账号',
        description: '先输入你的邮箱，我们会发送安全的认领链接，之后你可以继续进入日历导入。',
        emailLabel: '邮箱',
        emailPlaceholder: 'alice@example.com',
        submit: '给我发送认领链接',
        submitting: '发送中...',
        success: '认领链接已发送，请查收邮箱。',
        invalidOrExpiredError: '这个 WhatsApp 认领链接无效或已过期。请回到 WhatsApp 重新获取新的链接。',
        emailAlreadyExistsError: '该邮箱地址已被占用。请直接登录，或使用其他邮箱重新申请认领链接。',
        genericError: '暂时无法发送认领邮件，请稍后再试。',
        signInPrompt: '已经认领过账号？',
        signInLink: '去登录',
      },
      channelsIndex: {
        eyebrow: '第一阶段通道',
        title: '客户通道',
        description: '管理当前已经迁移到中立 ClawScale 客户壳层中的通道入口。',
        wechatPersonalTitle: '个人微信',
        wechatPersonalDescription: '连接、重新连接或归档你的个人微信通道。',
      },
      friends: {
        eyebrow: '好友',
        title: '好友管理',
        description: '分享你的好友链接，并管理当前好友。',
        linkTitle: '我的好友链接',
        linkDescription: '把这个链接发给对方，对方登录或注册后就可以直接加你为好友。',
        copyLink: '复制链接',
        copied: '链接已复制。',
        resetLink: '重置链接',
        disableLink: '停用当前链接',
        linkDisabled: '当前链接已停用。刷新页面时可以按现有规则创建新的链接。',
        inviteTitle: '添加好友',
        inviteDescription: '在你的账号面板里确认这条链接，然后直接添加对方为好友。',
        inviteTargetLabel: '目标账号',
        inviteSend: '添加好友',
        inviteSending: '添加中...',
        inviteSent: '好友已添加。',
        inviteAlreadyFriend: '这个账号已经在你的好友列表中。',
        inviteLoadFailure: '暂时无法加载这条好友链接。',
        inviteUnavailable: '这条邀请已不能再添加好友。',
        friendsTitle: '当前好友',
        emptyFriends: '暂无好友。',
        loading: '正在加载好友数据...',
        loadFailure: '暂时无法加载好友数据。',
        actionFailure: '暂时无法更新好友数据。',
        removeFriend: '删除好友',
        unknownFriend: '未知账号',
      },
      myAgent: {
        eyebrow: '智能体设置',
        title: '我的智能体',
        description: '自定义 Kap 和你互动时展示的人设、称呼和表达方式。',
        configured: '已配置',
        loadFailure: '暂时无法加载智能体设置。',
        saveFailure: '暂时无法保存智能体设置。',
        resetFailure: '暂时无法重置智能体设置。',
        saved: '智能体设置已保存。',
        reset: '重置',
        save: '保存',
        saving: '保存中...',
        basicIdentity: '基础身份',
        agentProfile: '智能体资料',
        proactiveMessages: '主动消息',
        memoryPersonalization: '记忆与个性化',
      },
      bindWechat: {
        blocked: {
          accessEyebrow: '账号访问',
          suspendedTitle: '你的 Kap 账号已被停用',
          suspendedDescription: '请先联系支持恢复访问权限，然后再绑定个人微信通道。',
          prerequisitesTitle: '先完成邮箱验证和订阅续费，再创建微信通道。',
          prerequisitesDescription: '先把账号要求的步骤完成，再回来创建或重新连接你的微信通道。',
          verifyEmail: '验证邮箱',
          renewSubscription: '续费订阅',
        },
        loadFailure: {
          title: '无法加载你的微信通道',
        },
        loading: {
          title: '正在加载你的微信通道',
          description: '我们正在检查当前 Kap 账号绑定的个人微信通道状态。',
        },
        statusDescriptions: {
          missing: '先创建通道，然后用你自己的微信发送配对码。',
          archived: '归档通道不会再转发消息。若要重新开始，请创建一个新的通道。',
          disconnected: '通道已经存在，但尚未连接。发送配对码即可让它重新上线。',
        },
        pairing: {
          codeLabel: '配对码',
          instructions: '添加 Coke 微信机器人，然后发送这个配对码。',
          preparing: '正在生成配对码...',
          expiresPrefix: '该配对码过期时间：',
          activeSuffix: '当前配对码仍然有效。',
        },
        connectedCard: {
          eyebrow: '已连接',
          descriptionWithIdentity: '微信 {identity} 已连接到这个 Kap 账号。',
          descriptionWithoutIdentity: '你的个人微信通道已连接并可正常使用。',
          accountOwnershipSuffix: '{name}，这个通道归属于你的 Kap 账号。',
        },
        errorCard: {
          eyebrow: '连接异常',
          fallbackDescription: '上一次连接尝试失败了。你可以重试，或归档这个通道。',
        },
        nextSteps: {
          title: '接下来可以做什么',
          missing: '为这个账号创建你的个人微信通道。',
          disconnected: '发送配对码，连接这个已存在的通道。',
          pending: '添加 Coke 微信机器人，发送配对码，然后继续用这个微信账号发送消息。',
          connected: '需要下线时，可以断开这个通道。',
          error: '重新走一次连接流程，或归档当前异常通道。',
          archived: '如果想重新开始，请创建一个新的通道。',
        },
        busyActions: {
          create: '创建中...',
          connect: '连接中...',
          refresh: '刷新中...',
          disconnect: '断开中...',
          reconnect: '重新连接中...',
          archive: '归档中...',
        },
        accountPrompt: '还没有账号？',
        createAccount: '创建一个',
        viewModel: {
          missing: {
            eyebrow: '尚未创建通道',
            title: '创建我的微信通道',
            description: '为这个 Kap 账号创建一个个人微信通道，然后通过配对码把它连接起来。',
            primaryActionLabel: '创建我的微信通道',
          },
          disconnected: {
            eyebrow: '通道已创建',
            title: '连接微信',
            description: '你的个人微信通道已经存在。发送配对码即可让它上线。',
            primaryActionLabel: '连接微信',
          },
          pending: {
            eyebrow: '正在配对',
            title: '发送配对码完成连接',
            description: '使用下方配对码把你的微信账号绑定到 Kap。',
            primaryActionLabel: '刷新配对码',
          },
          connected: {
            eyebrow: '已连接',
            title: '微信已连接',
            descriptionWithIdentity: '你的个人通道已使用 {identity} 连通。',
            descriptionWithoutIdentity: '你的个人微信通道已连接并可正常使用。',
            primaryActionLabel: '断开微信',
          },
          error: {
            eyebrow: '连接异常',
            title: '重新连接或归档通道',
            descriptionFallback: '上一次连接尝试失败。你可以重试，或归档这个通道。',
            primaryActionLabel: '重新连接',
            secondaryActionLabel: '归档通道',
          },
          archived: {
            eyebrow: '已归档',
            title: '这个微信通道已归档',
            description: '如果你还想继续使用微信，请重新创建一个新的个人通道。',
            primaryActionLabel: '重新创建我的微信通道',
          },
        },
      },
    },
    cokeUserPages: {
      renew: {
        title: '续订访问权限',
        preparing: '正在准备续费结账流程...',
        ready: '准备好后可重新进入结账流程。',
        signIn: '登录',
        backToSetup: '返回设置',
        genericError: '暂时无法发起续费，请稍后再试。',
      },
      paymentSuccess: {
        title: '支付完成',
        description: '我们已收到你的续费付款。返回账号后即可继续完成微信连接。',
        primaryCta: '前往微信设置',
        secondaryCta: '检查续费状态',
      },
      paymentCancel: {
        title: '支付已取消',
        description: '结账流程在付款完成前已取消。准备好后你可以再次尝试。',
        primaryCta: '重新发起续费',
        secondaryCta: '返回设置',
      },
    },
  },
};

declare global {
  interface Window {
    __COKE_LOCALE__?: Locale;
  }
}

function readSupportedLocale(value: string | null | undefined): Locale | null {
  const normalized = value?.trim().toLowerCase();
  if (!normalized) {
    return null;
  }

  if (normalized === 'zh' || normalized.startsWith('zh-')) {
    return 'zh';
  }

  if (normalized === 'en' || normalized.startsWith('en-')) {
    return 'en';
  }

  return null;
}

export function normalizeLocale(value: string | null | undefined): Locale {
  const parsedLocale = readSupportedLocale(value);
  if (parsedLocale) {
    return parsedLocale;
  }

  return DEFAULT_LOCALE;
}

export function detectLocaleFromNavigator(value: string | null | undefined): Locale {
  return normalizeLocale(value);
}

export function detectLocaleFromAcceptLanguage(value: string | null | undefined): Locale {
  if (!value) {
    return DEFAULT_LOCALE;
  }

  const candidates = value
    .split(',')
    .map((entry, index) => {
      const [range = '', ...params] = entry.trim().split(';');
      const qualityParam = params.find((param) => param.trim().startsWith('q='));
      const quality = qualityParam ? Number.parseFloat(qualityParam.split('=')[1] ?? '') : 1;

      return {
        index,
        quality: Number.isFinite(quality) ? quality : 1,
        range,
      };
    })
    .filter(({ range }) => range.length > 0)
    .map(({ index, quality, range }) => ({
      index,
      quality,
      locale: readSupportedLocale(range),
    }))
    .filter(({ locale, quality }) => locale !== null && quality > 0)
    .sort((left, right) => {
      if (right.quality !== left.quality) {
        return right.quality - left.quality;
      }

      return left.index - right.index;
    });

  return candidates[0]?.locale ?? DEFAULT_LOCALE;
}

export function resolveInitialLocale({
  cookieLocale,
  acceptLanguage,
}: {
  cookieLocale?: string | null;
  acceptLanguage?: string | null;
}): Locale {
  if (cookieLocale != null && cookieLocale !== '') {
    const supportedLocale = readSupportedLocale(cookieLocale);
    if (supportedLocale) {
      return supportedLocale;
    }
  }

  return detectLocaleFromAcceptLanguage(acceptLanguage);
}

function readPersistedLocale(): Locale | null {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return null;
  }

  try {
    const storedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    const supportedLocale = readSupportedLocale(storedLocale);
    if (supportedLocale) {
      return supportedLocale;
    }
  } catch {
    // Ignore storage failures and fall back to cookies or navigator language.
  }

  try {
    const cookieLocale = document.cookie
      .split(';')
      .map((entry) => entry.trim())
      .find((entry) => entry.startsWith(`${LOCALE_COOKIE_NAME}=`))
      ?.split('=')[1];

    return readSupportedLocale(cookieLocale);
  } catch {
    return null;
  }
}

export function detectClientLocale(): Locale {
  const persistedLocale = readPersistedLocale();
  if (persistedLocale) {
    return persistedLocale;
  }

  if (typeof navigator !== 'undefined') {
    return detectLocaleFromNavigator(navigator.language);
  }

  return DEFAULT_LOCALE;
}

export function getBootstrappedLocale(): Locale | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return readSupportedLocale(window[LOCALE_BOOTSTRAP_KEY]);
}
