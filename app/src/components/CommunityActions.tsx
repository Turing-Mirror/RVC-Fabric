import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useMenu, useNotify, type MenuItem } from "trm-ui";
import { useI18n } from "../i18n";
import { openExternal } from "../lib/plaza";
import { Btn } from "./ui";

type CommunityLinks = { enabled: boolean; accountUrl: string | null };
type AccountStatus = {
  signedIn: boolean;
  displayName: string | null;
  email: string | null;
  offline: boolean;
};
type AccountAction = "sign_in" | "sign_out";

export function useCommunityAccount() {
  const [links, setLinks] = useState<CommunityLinks>();
  const [account, setAccount] = useState<AccountStatus>();
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<AccountAction>();
  const { t } = useI18n();
  const { tip } = useNotify();

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    let active = true;
    async function load() {
      try {
        const next = await invoke<CommunityLinks>("community_links");
        if (!active || !next.enabled) return;
        setLinks(next);
        const status = await invoke<AccountStatus>("community_account_status");
        if (active) setAccount(status);
      } catch {
        // A missing session still lets the user sign in.
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function run(next: AccountAction) {
    setAction(next);
    try {
      const status = await invoke<AccountStatus>(next === "sign_in" ? "community_account_sign_in" : "community_account_sign_out");
      setAccount(status);
    } catch (error) {
      if (typeof error === "object" && error !== null && "code" in error && error.code === "canceled") return;
      tip(t(next === "sign_in" ? "community.signInFailed" : "community.signOutFailed"));
    } finally {
      setAction(undefined);
    }
  }

  return { links, account, loading, action, run };
}

export type CommunityAccount = ReturnType<typeof useCommunityAccount>;

export function CommunityActions({ auth, onPublish, onSubmissions, onOwned }: {
  auth: CommunityAccount;
  onPublish: () => void;
  onSubmissions: () => void;
  onOwned: () => void;
}) {
  const { t } = useI18n();
  const { tip } = useNotify();
  const menu = useMenu();
  const { links, account, loading, action, run } = auth;
  if (!links) return null;

  const name = account?.displayName || account?.email || t("community.account");
  const items: MenuItem[] = [];
  if (account?.email && account.email !== name) {
    items.push({ id: "email", label: account.email, disabled: true });
  }
  items.push({ id: "submissions", label: t("community.submissions"), onSelect: onSubmissions });
  items.push({ id: "owned", label: t("publication.myModels"), onSelect: onOwned });
  if (links.accountUrl) {
    const url = links.accountUrl;
    items.push({
      id: "account", label: t("community.manageAccount"),
      onSelect: () => void openExternal(url).catch(() => tip(t("community.linkFailed"))),
    });
  }
  items.push({ id: "signOut", label: t("community.signOut"), onSelect: () => void run("sign_out") });

  return (
    <>
      <Btn onClick={onPublish}>{t("community.publish")}</Btn>
      {account?.signedIn ? (
        <Btn busy={action === "sign_out"} ariaLabel={name} onClick={(event) => menu.open(event.currentTarget, items)}>
          <span className="block max-w-40 truncate" title={name}>{name}</span>
        </Btn>
      ) : (
        <Btn disabled={loading} busy={action === "sign_in"} onClick={() => void run("sign_in")}>{t("community.signIn")}</Btn>
      )}
      {menu.node}
    </>
  );
}
