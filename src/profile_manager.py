"""CRUD de perfis sobre SettingsManager."""
from __future__ import annotations


class ProfileManager:
    def __init__(self, settings):
        self.s = settings

    def names(self) -> list[str]:
        return sorted(self.s.data.get("profiles", {}).keys())

    def get(self, name: str) -> dict | None:
        return self.s.data.get("profiles", {}).get(name)

    def create(self, name: str, values: dict | None = None) -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("Nome do perfil vazio.")
        if name in self.s.data["profiles"]:
            raise ValueError(f"Perfil '{name}' ja existe.")
        base = values or {"gamma": self.s.get("gamma", 1.0),
                          "brightness": self.s.get("brightness", 50.0),
                          "contrast": self.s.get("contrast", 50.0),
                          "monitor": self.s.get("monitor"),
                          "gpu": self.s.get("gpu", "")}
        self.s.data["profiles"][name] = dict(base)
        self.s.save()

    def update(self, name: str, values: dict) -> None:
        if name not in self.s.data["profiles"]:
            raise KeyError(name)
        self.s.data["profiles"][name].update(values)
        self.s.save()

    def rename(self, old: str, new: str) -> None:
        new = (new or "").strip()
        if not new:
            raise ValueError("Novo nome vazio.")
        if new in self.s.data["profiles"]:
            raise ValueError(f"Perfil '{new}' ja existe.")
        self.s.data["profiles"][new] = self.s.data["profiles"].pop(old)
        if self.s.get("active_profile") == old:
            self.s.set("active_profile", new)
        else:
            self.s.save()

    def delete(self, name: str) -> None:
        if name not in self.s.data["profiles"]:
            raise KeyError(name)
        if len(self.s.data["profiles"]) <= 1:
            raise ValueError("Nao e possivel excluir o ultimo perfil.")
        del self.s.data["profiles"][name]
        if self.s.get("active_profile") == name:
            self.s.set("active_profile", self.names()[0])
        else:
            self.s.save()

    def duplicate(self, name: str, new_name: str | None = None) -> str:
        src = self.get(name)
        if src is None:
            raise KeyError(name)
        base = new_name or f"{name} (copia)"
        cand, i = base, 2
        while cand in self.s.data["profiles"]:
            cand = f"{base} {i}"
            i += 1
        self.s.data["profiles"][cand] = dict(src)
        self.s.save()
        return cand

    def snapshot_current(self, name: str, gamma, brightness, contrast,
                         monitor, gpu) -> None:
        self.update(name, {"gamma": gamma, "brightness": brightness,
                           "contrast": contrast, "monitor": monitor, "gpu": gpu})
