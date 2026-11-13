"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, ErrorNote, Modal, PageHeader, Spinner, TextArea, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { minutesToText } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import type { Category } from "@/lib/types";

interface Skill {
  id: string;
  name: string;
}

function CategoryForm({ category, skills, onDone }: { category?: Category; skills: Skill[]; onDone: () => void }) {
  const [name, setName] = useState(category?.name ?? "");
  const [description, setDescription] = useState(category?.description ?? "");
  const [duration, setDuration] = useState(String(category?.default_duration_minutes ?? 60));
  const [selected, setSelected] = useState<string[]>(category?.required_skills.map((s) => s.id) ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useAction(
    () => {
      const body = { name: name.trim(), description: description.trim(), default_duration_minutes: Number(duration), skill_ids: selected };
      return category ? api.patch(`/categories/${category.id}`, body) : api.post("/categories", body);
    },
    { success: "Category saved.", onSuccess: onDone, silentError: true },
  );
  const server = save.error instanceof ApiError ? save.error.fields : {};
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (name.trim().length < 2) found.name = "Name is required.";
        if (!Number.isInteger(Number(duration)) || Number(duration) < 30) found.duration = "At least 30 minutes.";
        setErrors(found);
        if (!Object.keys(found).length && !save.isPending) save.mutate(undefined);
      }}
    >
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name ?? server.name} />
      <TextArea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      <TextField label="Default duration (minutes)" type="number" min={30} value={duration} onChange={(e) => setDuration(e.target.value)} error={errors.duration ?? server.default_duration_minutes} />
      <fieldset style={{ border: "1px solid var(--border)", borderRadius: 8 }}>
        <legend>Required skills (all needed)</legend>
        <div className="row">
          {skills.map((s) => (
            <label className="check" key={s.id}>
              <input type="checkbox" checked={selected.includes(s.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, s.id] : selected.filter((x) => x !== s.id))} />
              {s.name}
            </label>
          ))}
          {skills.length === 0 ? <span className="muted">Create skills first.</span> : null}
        </div>
      </fieldset>
      {save.error && !Object.keys(server).length ? <ErrorNote error={save.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function View() {
  const categories = useApiQuery<Category[]>("/categories");
  const skills = useApiQuery<Skill[]>("/skills");
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [skillName, setSkillName] = useState("");
  const [skillError, setSkillError] = useState<string | null>(null);
  const toggle = useAction((c: Category) => api.patch(`/categories/${c.id}`, { is_enabled: !c.is_enabled }), { success: "Category updated." });
  const addSkill = useAction(() => api.post("/skills", { name: skillName.trim() }), { success: "Skill added.", onSuccess: () => setSkillName("") });
  const removeSkill = useAction((id: string) => api.del(`/skills/${id}`), { success: "Skill removed." });
  return (
    <>
      <PageHeader title="Categories & skills" actions={<Button onClick={() => setEditing("new")}>New category</Button>} />
      {categories.isLoading ? <Spinner /> : null}
      <ErrorNote error={categories.error} />
      <div className="stack">
        <Card title="Service categories">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Required skills</th>
                  <th>Default duration</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {categories.data?.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      <div className="muted small">{c.description}</div>
                    </td>
                    <td>{c.required_skills.map((s) => s.name).join(", ") || "—"}</td>
                    <td>{minutesToText(c.default_duration_minutes)}</td>
                    <td>{c.is_enabled ? "Enabled" : "Disabled (history only)"}</td>
                    <td className="row">
                      <Button small variant="secondary" onClick={() => setEditing(c)}>
                        Edit
                      </Button>
                      <Button small variant="secondary" loading={toggle.isPending} onClick={() => toggle.mutate(c)}>
                        {c.is_enabled ? "Disable" : "Enable"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Skill catalog">
          <div className="row">
            {skills.data?.map((s) => (
              <span className="badge" key={s.id}>
                {s.name}{" "}
                <button className="btn btn-ghost btn-sm" aria-label={`Remove skill ${s.name}`} onClick={() => removeSkill.mutate(s.id)}>
                  ✕
                </button>
              </span>
            ))}
          </div>
          <form
            className="row"
            style={{ marginTop: "0.75rem" }}
            onSubmit={(e) => {
              e.preventDefault();
              if (skillName.trim().length < 2) return setSkillError("Skill name needs 2+ characters.");
              setSkillError(null);
              if (!addSkill.isPending) addSkill.mutate(undefined);
            }}
          >
            <TextField label="New skill" value={skillName} onChange={(e) => setSkillName(e.target.value)} error={skillError} />
            <Button type="submit" loading={addSkill.isPending} style={{ alignSelf: "end" }}>
              Add skill
            </Button>
          </form>
        </Card>
      </div>
      <Modal title={editing === "new" ? "New category" : "Edit category"} open={editing !== null} onClose={() => setEditing(null)}>
        {editing ? <CategoryForm category={editing === "new" ? undefined : editing} skills={skills.data ?? []} onDone={() => setEditing(null)} /> : null}
      </Modal>
    </>
  );
}

export default function CategoriesPage() {
  return (
    <AuthGuard roles={["ADMIN"]}>
      <View />
    </AuthGuard>
  );
}
