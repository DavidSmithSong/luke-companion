import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY

export const supabase =
  supabaseUrl && supabaseKey && !supabaseUrl.startsWith('https://your-project')
    ? createClient(supabaseUrl, supabaseKey)
    : null

export function getReaderId() {
  let id = localStorage.getItem('reader_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('reader_id', id)
  }
  return id
}

export async function syncFromCloud(chapter, keys) {
  if (!supabase) return
  const readerId = getReaderId()
  const { data, error } = await supabase
    .from('reader_answers')
    .select('question_index, answer')
    .eq('reader_id', readerId)
    .eq('chapter', chapter)
  if (error) { console.warn('Supabase sync error:', error.message); return }
  if (!data) return
  for (const row of data) {
    const key = keys[row.question_index]
    if (key && row.answer) {
      // only overwrite if cloud is newer (we don't have timestamps client-side,
      // so only fill if localStorage is empty)
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, row.answer)
      }
    }
  }
}

export async function saveToCloud(chapter, questionIndex, answer) {
  if (!supabase) return
  const readerId = getReaderId()
  await supabase.from('reader_answers').upsert(
    { reader_id: readerId, chapter, question_index: questionIndex, answer, updated_at: new Date().toISOString() },
    { onConflict: 'reader_id,chapter,question_index' }
  )
}
