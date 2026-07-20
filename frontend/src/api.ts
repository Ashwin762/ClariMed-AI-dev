// frontend/src/api.ts
// Typed client for the real ClariMed backend. Centralizes every fetch call
// so components don't hand-roll FormData/JSON parsing individually.

export type BodyPart =
  | 'eye' | 'skin' | 'nail' | 'oral' | 'general'
  | 'dental' | 'ent' | 'hair' | 'respiratory' | 'digestive' | 'musculoskeletal'
  | 'neurological' | 'urinary' | 'reproductive' | 'cardiovascular';

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

export interface EmergencyInfo {
  is_emergency: boolean;
  national_emergency_number: string;
  hospitals: Clinic[];
}

export interface ScreenResponse {
  success: boolean;
  screening_id?: string;
  body_part?: string;
  result?: ScreeningResult;
  guidance?: string;
  guidance_source?: 'curated_kb' | 'general_llm_unverified' | 'unavailable';
  language?: string;
  interpreted_symptoms?: string[];
  interpreted_redflags?: string[];
  vision_detected_symptoms?: string[];
  vision_other_observations?: string;
  emergency?: EmergencyInfo;
  image?: { provided: boolean; heatmap_overlay: string | null; brightness?: number; relevance_warning?: string };
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

export async function suggestBodyPart(description: string): Promise<BodyPart> {
  const fd = new FormData();
  fd.append('description', description);
  const res = await fetch(`${BASE}/api/suggest-body-part`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(`Suggestion failed (${res.status})`);
  const data = await res.json();
  return data.suggested_body_part as BodyPart;
}

export interface ImageSymptomSuggestion {
  success: boolean;
  suggested_symptoms: string[];
  based_on_conditions: { id: string; name: string; img_score: number }[];
  stage?: string;
  message?: string;
}

export async function suggestSymptomsFromImage(bodyPart: BodyPart, file: File): Promise<ImageSymptomSuggestion> {
  const fd = new FormData();
  fd.append('body_part', bodyPart);
  fd.append('file', file);
  const res = await fetch(`${BASE}/api/suggest-symptoms-from-image`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Suggestion failed (${res.status})`);
  }
  return res.json();
}

export interface BodyPartGuess {
  success: boolean;
  guessed_body_part: BodyPart | null;
  confidence: number | null;
  all_scores: Record<string, number> | null;
}

export async function guessBodyPartFromImage(file: File): Promise<BodyPartGuess> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`${BASE}/api/guess-body-part-from-image`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Guess failed (${res.status})`);
  }
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
  language?: string;
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
  fd.append('language', params.language || 'en');
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

// ---------------------------------------------------------------------------
// Doctor portal (per-doctor accounts, department-scoped)
// ---------------------------------------------------------------------------

export interface DoctorScreening {
  id: string;
  created_at: string;
  body_part: string | null;
  symptoms: string[];
  redflags: string[];
  top_condition_name: string | null;
  top_confidence_pct: number | null;
  confidence_tier: string | null;
  risk_level: string | null;
  out_of_coverage: number | null;
  guidance: string | null;
  vision_observations: string | null;
}

export interface ClinicalNote {
  id: string;
  created_at: string;
  note: string;
}

export interface DoctorAppointment {
  id: string;
  created_at: string;
  screening_id: string | null;
  patient_name: string | null;
  patient_email: string | null;
  specialist_name: string;
  clinic_name: string | null;
  slot: string;
  status: string;
  assigned_doctor_id: string | null;
  is_mine: boolean;
  is_pooled: boolean;
  screening: DoctorScreening | null;
  notes: ClinicalNote[];
}

export interface DoctorProfile {
  id: string;
  name: string;
  email: string;
  department: string;
}

const DOCTOR_TOKEN_KEY = 'clarimed_doctor_token';

export function getStoredDoctorToken(): string | null {
  try { return localStorage.getItem(DOCTOR_TOKEN_KEY); } catch { return null; }
}
export function storeDoctorToken(token: string) {
  try { localStorage.setItem(DOCTOR_TOKEN_KEY, token); } catch { /* ignore */ }
}
export function clearDoctorToken() {
  try { localStorage.removeItem(DOCTOR_TOKEN_KEY); } catch { /* ignore */ }
}

export async function fetchDepartments(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/doctor/departments`);
  if (!res.ok) throw new Error('Could not load departments');
  const data = await res.json();
  return data.departments as string[];
}

export async function registerDoctor(
  name: string, email: string, password: string, department: string
): Promise<{ doctor: DoctorProfile; backlog_assigned: number }> {
  const fd = new FormData();
  fd.append('name', name);
  fd.append('email', email);
  fd.append('password', password);
  fd.append('department', department);
  const res = await fetch(`${BASE}/api/doctor/register`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Registration failed');
  }
  return res.json();
}

export async function loginDoctor(
  email: string, password: string
): Promise<{ token: string; doctor: DoctorProfile }> {
  const fd = new FormData();
  fd.append('email', email);
  fd.append('password', password);
  const res = await fetch(`${BASE}/api/doctor/login`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error('Invalid email or password');
  return res.json();
}

export async function fetchDoctorMe(token: string): Promise<DoctorProfile> {
  const res = await fetch(`${BASE}/api/doctor/me`, { headers: { 'X-Doctor-Token': token } });
  if (!res.ok) throw new Error('Session expired');
  const data = await res.json();
  return data.doctor as DoctorProfile;
}

export async function logoutDoctor(token: string): Promise<void> {
  await fetch(`${BASE}/api/doctor/logout`, { method: 'POST', headers: { 'X-Doctor-Token': token } });
}

export async function fetchDoctorAppointments(
  token: string
): Promise<{ doctor: DoctorProfile; appointments: DoctorAppointment[] }> {
  const res = await fetch(`${BASE}/api/doctor/appointments`, { headers: { 'X-Doctor-Token': token } });
  if (res.status === 401) throw new Error('SESSION_EXPIRED');
  if (!res.ok) throw new Error(`Failed to load appointments (${res.status})`);
  return res.json();
}

export async function claimAppointment(token: string, appointmentId: string): Promise<void> {
  const fd = new FormData();
  fd.append('appointment_id', appointmentId);
  const res = await fetch(`${BASE}/api/doctor/claim`, {
    method: 'POST', headers: { 'X-Doctor-Token': token }, body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Could not claim appointment');
  }
}

export async function addClinicalNote(token: string, appointmentId: string, note: string): Promise<ClinicalNote> {
  const fd = new FormData();
  fd.append('appointment_id', appointmentId);
  fd.append('note', note);
  const res = await fetch(`${BASE}/api/doctor/notes`, {
    method: 'POST', headers: { 'X-Doctor-Token': token }, body: fd,
  });
  if (!res.ok) throw new Error(`Failed to save note (${res.status})`);
  const data = await res.json();
  return data.note as ClinicalNote;
}

// ---------------------------------------------------------------------------
// Chat — a conversational presentation layer over the exact same
// safety-tested backend logic the step-by-step wizard uses. See
// backend/app/chat_orchestrator.py for the full design reasoning.
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatQuestionResponse {
  type: 'question';
  message: string;
  body_part: BodyPart | null;
}

export interface ChatResultResponse extends ScreenResponse {
  type: 'result';
}

export type ChatTurnResponse = ChatQuestionResponse | ChatResultResponse;

export interface SupportedLanguage {
  label: string;
  locale: string;
}

export async function fetchLanguages(): Promise<Record<string, SupportedLanguage>> {
  const res = await fetch(`${BASE}/api/languages`);
  if (!res.ok) throw new Error('Could not load supported languages');
  const data = await res.json();
  return data.languages;
}

export async function translateUIStrings(strings: Record<string, string>, language: string): Promise<Record<string, string>> {
  const fd = new FormData();
  fd.append('strings_json', JSON.stringify(strings));
  fd.append('language', language);
  const res = await fetch(`${BASE}/api/translate-ui-strings`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error('Could not translate UI strings');
  const data = await res.json();
  return data.strings;
}

export async function sendChatTurn(params: {
  messages: ChatMessage[];
  bodyPart: BodyPart | null;
  language?: string;
  patientName?: string;
  patientEmail?: string;
  consentGiven: boolean;
  file?: File | null;
}): Promise<ChatTurnResponse> {
  const fd = new FormData();
  fd.append('messages_json', JSON.stringify(params.messages));
  fd.append('body_part', params.bodyPart || '');
  fd.append('language', params.language || 'en');
  fd.append('patient_name', params.patientName || '');
  fd.append('patient_email', params.patientEmail || '');
  fd.append('consent_given', String(params.consentGiven));
  if (params.file) fd.append('file', params.file);

  const res = await fetch(`${BASE}/api/chat`, { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Chat request failed (${res.status})`);
  }
  return res.json();
}