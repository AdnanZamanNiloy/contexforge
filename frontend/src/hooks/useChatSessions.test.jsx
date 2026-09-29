import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'

const api = {
  listChatSessions: vi.fn(),
  createChatSession: vi.fn(),
  deleteChatSession: vi.fn(),
}

vi.mock('../services/api', () => ({
  listChatSessions: (...args) => api.listChatSessions(...args),
  createChatSession: (...args) => api.createChatSession(...args),
  deleteChatSession: (...args) => api.deleteChatSession(...args),
}))

import { useChatSessions } from './useChatSessions'

function mountHook(projectId) {
  let latest
  function Probe({ id }) {
    latest = useChatSessions(id)
    return null
  }
  render(<Probe id={projectId} />)
  return () => latest
}

beforeEach(() => {
  api.listChatSessions.mockReset()
  api.createChatSession.mockReset()
  api.deleteChatSession.mockReset()
})

describe('useChatSessions', () => {
  it("loads a project's sessions and activates the most recent", async () => {
    api.listChatSessions.mockResolvedValue({
      sessions: [
        { id: 'chat_new', project_id: 'proj_1', title: '', message_count: 2 },
        { id: 'chat_old', project_id: 'proj_1', title: '', message_count: 1 },
      ],
      total: 2,
    })

    const chat = mountHook('proj_1')
    await waitFor(() => expect(chat().loading).toBe(false))
    expect(chat().sessions).toHaveLength(2)
    expect(chat().activeSessionId).toBe('chat_new')
  })

  it('does not call the backend without a project', async () => {
    mountHook(null)
    await act(async () => {})
    expect(api.listChatSessions).not.toHaveBeenCalled()
  })

  it('ensureSession creates a session once and reuses it', async () => {
    api.listChatSessions.mockResolvedValue({ sessions: [], total: 0 })
    api.createChatSession.mockResolvedValue({ id: 'chat_fresh', project_id: 'proj_1' })

    const chat = mountHook('proj_1')
    await waitFor(() => expect(chat().loading).toBe(false))

    let id
    await act(async () => {
      id = await chat().ensureSession()
    })
    expect(id).toBe('chat_fresh')

    // A second call while active returns the existing id without re-creating.
    let again
    await act(async () => {
      again = await chat().ensureSession()
    })
    expect(again).toBe('chat_fresh')
    expect(api.createChatSession).toHaveBeenCalledTimes(1)
  })

  it('removeSession deletes and moves the active session on', async () => {
    api.listChatSessions.mockResolvedValue({
      sessions: [
        { id: 'chat_a', project_id: 'proj_1', title: '' },
        { id: 'chat_b', project_id: 'proj_1', title: '' },
      ],
      total: 2,
    })
    api.deleteChatSession.mockResolvedValue(null)

    const chat = mountHook('proj_1')
    await waitFor(() => expect(chat().activeSessionId).toBe('chat_a'))

    await act(async () => {
      await chat().removeSession('chat_a')
    })
    expect(api.deleteChatSession).toHaveBeenCalledWith('chat_a')
    expect(chat().sessions.map((s) => s.id)).toEqual(['chat_b'])
    expect(chat().activeSessionId).toBe('chat_b')
  })
})
