# -*- coding: utf-8 -*-
"""Voice-config profile logic mixed into MainApp (Plan A M3a).

Applies a model's active profile (voice + FX + perf) by reflecting its values
into the existing settings/dock Tk vars and reusing the production hot-push
path (``_push_hot_params``) — so the engine applies the whole profile live,
with no engine change. Perf keys are cold (take effect on the next start).

UI (bind / switch / cancel panel) is M3b; this layer already enables the paid
delivery loop: drop a ``.tmvp`` into the model's ``profiles/`` + point
``active_profile`` at it, and it applies on model select.
"""

from __future__ import annotations

from typing import Optional

from launcher import profiles as P
from launcher.config_store import save_config

# cfg-key -> the settings/dock Tk var attribute that mirrors it. Reflecting a
# profile into these vars (then calling _push_hot_params, which re-collects from
# them) keeps cfg, UI, and the worker consistent. Verified against
# settings_page._collect_settings_into_cfg.
_PROFILE_SCALAR_VARS: dict[str, str] = {
    "pitch": "var_pitch",
    "formant": "var_formant",
    "f0method": "var_f0",
    "threhold": "var_threhold",
    "index_rate": "var_index_rate",
    "rms_mix_rate": "var_rms",
    "block_time": "var_block",
    "crossfade_length": "var_crossfade",
    "extra_time": "var_extra",
    "fx_enabled": "var_fx_enabled",
    "fx_gate_enabled": "var_fx_gate_en",
    "fx_gate_threshold_db": "var_fx_gate_thr",
    "fx_gate_release_ms": "var_fx_gate_rel",
    "fx_gate_hold_ms": "var_fx_gate_hold",
    "fx_gate_range_db": "var_fx_gate_range",
    "fx_comp_enabled": "var_fx_comp_en",
    "fx_comp_threshold_db": "var_fx_comp_thr",
    "fx_comp_ratio": "var_fx_comp_ratio",
    "fx_comp_attack_ms": "var_fx_comp_att",
    "fx_comp_release_ms": "var_fx_comp_rel",
    "fx_comp_makeup_db": "var_fx_comp_mu",
    "fx_eq_enabled": "var_fx_eq_en",
    "fx_eq_preset": "var_fx_eq_preset",
    "fx_out_gain_db": "var_fx_out_gain",
}
_PERF_KEYS = frozenset(P.PERF_KEYS)


class ProfilesMixin:
    # -- current model helpers --------------------------------------------
    def _current_model(self) -> Optional[dict]:
        if not getattr(self, "models", None):
            return None
        try:
            return self.models[self.model_idx]
        except (IndexError, TypeError):
            return None

    def _current_model_dir(self) -> Optional[str]:
        m = self._current_model()
        if not m or m.get("source") != "user_data" or not m.get("dir"):
            return None
        return str(m["dir"])

    # -- apply -------------------------------------------------------------
    def _reflect_updates_to_ui(self, updates: dict) -> None:
        """Push profile values into the mirror Tk vars (+ cfg) so the next
        _push_hot_params re-collects the profile, not the stale UI state."""
        self._loading_voice = True
        try:
            for key, val in updates.items():
                self.cfg[key] = val
                if key == "fx_eq_gains":
                    bands = getattr(self, "var_fx_eq_gains", None)
                    if bands and isinstance(val, (list, tuple)) and len(val) == 5:
                        for i in range(5):
                            try:
                                bands[i].set(float(val[i]))
                            except Exception:
                                pass
                    continue
                attr = _PROFILE_SCALAR_VARS.get(key)
                var = getattr(self, attr, None) if attr else None
                if var is not None:
                    try:
                        var.set(val)
                    except Exception:
                        pass
        finally:
            self._loading_voice = False

    def _apply_active_profile(self) -> bool:
        """Overlay the current model's active profile onto UI + engine.

        Returns True when a profile was applied (False = on default). Models
        without an active profile are untouched (early return), keeping the
        blast radius to exactly the feature's users.
        """
        d = self._current_model_dir()
        if not d:
            return False
        try:
            prof = P.resolve_active_profile(d)
        except Exception:
            prof = None
        updates = P.profile_to_config_updates(prof)
        if not updates:
            return False
        self._reflect_updates_to_ui(updates)
        # reuse the production hot path (collects vars -> cfg -> worker + save)
        try:
            self._push_hot_params()
        except Exception:
            try:
                save_config(self.cfg)
            except Exception:
                pass
        # perf keys are cold: hint if a running stream needs a restart
        if self.vc_running and any(k in _PERF_KEYS for k in updates):
            try:
                self._set_status_visual(
                    "live", "档案已应用", "性能项需重新开启变声后完全生效"
                )
            except Exception:
                pass
        return True

    # -- management (called by M3b UI) ------------------------------------
    def _profiles_for_current(self) -> list[dict]:
        d = self._current_model_dir()
        return P.list_profiles(d) if d else []

    def _active_profile_id_current(self) -> str:
        d = self._current_model_dir()
        return P.get_active_profile_id(d) if d else ""

    def _switch_profile(self, profile_id: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        P.set_active_profile_id(d, profile_id)
        if profile_id:
            return self._apply_active_profile()
        # cleared -> revert to the model's default voice params
        m = self._current_model()
        if m is not None:
            try:
                self._apply_model_voice_params(m, push_remote=True)
            except Exception:
                pass
        return False

    def _clear_profile(self) -> None:
        self._switch_profile("")

    def _save_current_as_profile(
        self, name: str, *, source: str = "self", activate: bool = True
    ) -> Optional[str]:
        """Snapshot the current settings into a new profile bound to this model."""
        d = self._current_model_dir()
        if not d:
            return None
        try:
            self._collect_settings_into_cfg()
        except Exception:
            pass
        m = self._current_model() or {}
        prof = P.config_to_profile(
            self.cfg, name, source=source, for_model=str(m.get("name") or "")
        )
        P.save_profile(d, prof)
        if activate:
            P.set_active_profile_id(d, prof["id"])
        return prof["id"]

    def _import_profile(self, src_path: str, *, activate: bool = True) -> Optional[str]:
        """Import an external .tmvp into the current model's profiles/."""
        d = self._current_model_dir()
        if not d:
            return None
        import json

        try:
            with open(src_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return None
        prof = P.validate_profile(raw)
        if prof is None:
            return None
        P.save_profile(d, prof)
        if activate:
            P.set_active_profile_id(d, prof["id"])
            self._apply_active_profile()
        return prof["id"]

    def _delete_profile(self, profile_id: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        was_active = P.get_active_profile_id(d) == profile_id
        ok = P.delete_profile(d, profile_id)
        if ok and was_active:
            m = self._current_model()
            if m is not None:
                try:
                    self._apply_model_voice_params(m, push_remote=True)
                except Exception:
                    pass
        return ok

    def _export_profile(self, profile_id: str, dest_path: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        prof = P.load_profile(d, profile_id)
        if prof is None:
            return False
        import json

        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(prof, f, ensure_ascii=False, indent=2)
        except Exception:
            return False
        return True
