// frontend/src/api.ts
// Typed client for the real ClariMed backend. Centralizes every fetch call
// so components don't hand-roll FormData/JSON parsing individually.

export type BodyPart =
  | 'eye' | 'skin' | 'nail' | 'oral' | 'general'
  | 'dental' | 'ent' | 'hair' | 'respiratory' | 'digestive' | 'musculoskeletal';

export interface ConfigResponse {
  body_parts: BodyPart[];
  symptoms: Record<BodyPart, string[]>;
  redflags: Record<BodyPart, string[]>;
}

export interface Candidate {
  id: string;
  name: string;
  specialist: string;
  emergency_possible: boolean;
  fused_raw: number;
  img_score: number | null;
  sym_score: number;
  image_relevant: boolean;
  matched_keywords: string[];
  /** Relative ranking share only — NOT a probability. Used for bar widths. */
  share_pct: number;
  /** Absolute fit of symptoms+image to this condition, 0..1 */
  strength_raw: number;
  /** "Strong match" | "Moderate match" | "Weak match" */
  match_strength: string;
}

export interface Evidence {
  symptoms_reported: number;
  image_provided: boolean;
  matched_signals: number;
  candidates_considered: number;
  separation: number;
}

export interface ScreeningResult {
  body_part: string;
  candidates: Candidate[];
  top: Candidate | null;
  out_of_coverage: boolean;
  /** False when evidence is too thin to rank candidates meaningfully. */
  ranking_reliable: boolean;
  evidence: Evidence;
  risk_level: 'green' | 'yellow' | 'red';
  risk_reason: string;
}

export interface Clinic {
  name: string;
  distance: string;
  clinic: string;
  phone: string;
  lat?: number;
  lng?: number;
}

export interface ScreenResponse {
  success: boolean;
  screening_id?: string;
  body_part?: string;
  result?: ScreeningResult;
  guidance?: string;
  guidance_source?: 'curated_kb' | 'general_llm_unverified' | 'unavailable';
  interpreted_symptoms?: string[];
  image?: { provided: boolean; heatmap_overlay: string | null; brightness?: number };
  healthcare_network?: Clinic[];
  routed_specialist?: string;
  metadata?: { risk_level: string; risk_reason: string; regulatory_disclaimer: string };
  // present only on quality-check failure:
  stage?: string;
  issues?: string[];
  message?: string;
}

export interface HistoryItem {
  id: string;
  created_at: string;
  patient_name: string | null;
  patient_email: string | null;
  body_part: string;
  top_condition_name: string | null;
  /** DB column names, retained for schema stability. `confidence_tier` now
   *  stores the match-strength label (e.g. "Moderate match"). */
  top_confidence_pct: number | null;
  confidence_tier: string | null;
  risk_level: string;
  out_of_coverage: number;
}

const BASE = ''; // relative — Vite dev proxy forwards /api/* to the backend

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch(`${BASE}/api/config`);
  if (!res.ok) throw new Error(`Config fetch failed (${res.status})`);
  return res.json();
}

export interface PrivacyPolicy {
  policy_version: string;
  image_handling: string;
  what_we_store: string[];
  what_we_never_store: string[];
  your_rights: string[];
  ai_disclaimer: string;
  scope_limitation: string;
}

export async function fetchPrivacyPolicy(): Promise<PrivacyPolicy> {
  const res = await fetch(`${BASE}/api/privacy/policy`);
  if (!res.ok) throw new Error(`Policy fetch failed (${res.status})`);
  return res.json();
}

export async function giveConsent(patientEmail: string): Promise<{ consent_id: string }> {
  const fd = new FormData();
  fd.append('patient_email', patientEmail);
  fd.append('consent_image_processing', 'true');
  fd.append('consent_data_storage', 'true');
  const res = await fetch(`${BASE}/api/privacy/consent`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`Consent failed (${res.status})`);
  return res.json();
}

export async function deleteMyData(patientEmail: string): Promise<{ success: boolean; deleted: Record<string, number> }> {
  const res = await fetch(`${BASE}/api/privacy/delete?patient_email=${encodeURIComponent(patientEmail)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Deletion failed (${res.status})`);
  return res.json();
}

export async function submitScreening(params: {
  bodyPart: BodyPart;
  symptoms: string[];
  redflags: string[];
  transcript: string;
  patientName: string;
  patientEmail: string;
  file: File | null;
  consentGiven: boolean;
}): Promise<ScreenResponse> {
  const fd = new FormData();
  fd.append('body_part', params.bodyPart);
  fd.append('symptoms_json', JSON.stringify(params.symptoms));
  fd.append('redflags_json', JSON.stringify(params.redflags));
  fd.append('transcript', params.transcript);
  fd.append('patient_name', params.patientName);
  fd.append('patient_email', params.patientEmail);
  fd.append('consent_given', String(params.consentGiven));
  if (params.file) fd.append('file', params.file);

  const res = await fetch(`${BASE}/api/screen`, { method: 'POST', body: fd });
  return res.json();
}

export async function fetchHistory(patientEmail?: string): Promise<HistoryItem[]> {
  const url = patientEmail
    ? `${BASE}/api/history?patient_email=${encodeURIComponent(patientEmail)}`
    : `${BASE}/api/history`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`History fetch failed (${res.status})`);
  const data = await res.json();
  return data.history;
}

export function reportDownloadUrl(screeningId: string): string {
  return `${BASE}/api/report/${screeningId}`;
}

export async function bookAppointment(params: {
  specialistName: string;
  slot: string;
  screeningId?: string;
  clinicName?: string;
  patientName?: string;
  patientEmail?: string;
}): Promise<{ success: boolean; appointment_id: string; status: string }> {
  const fd = new FormData();
  fd.append('specialist_name', params.specialistName);
  fd.append('slot', params.slot);
  fd.append('screening_id', params.screeningId || '');
  fd.append('clinic_name', params.clinicName || '');
  fd.append('patient_name', params.patientName || '');
  fd.append('patient_email', params.patientEmail || '');
  const res = await fetch(`${BASE}/api/book-appointment`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`Booking failed (${res.status})`);
  return res.json();
}

export async function downloadReport(screeningId: string, filenameHint = 'ClariMed_Report.pdf') {
  const res = await fetch(reportDownloadUrl(screeningId));
  if (!res.ok) throw new Error(`Report download failed (${res.status})`);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filenameHint;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}