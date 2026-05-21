import * as mockApi from './mockApi'
import * as httpApi from './httpApi'

const useMock = import.meta.env.VITE_USE_MOCK_API === 'true'

export const createTask = useMock ? mockApi.createTask : httpApi.createTask
export const getTask = useMock ? mockApi.getTask : httpApi.getTask
export const submitClarification = useMock
  ? mockApi.submitClarification
  : httpApi.submitClarification
export const generateOutline = useMock
  ? mockApi.generateOutline
  : httpApi.generateOutline

export const apiModeLabel = useMock ? 'Mock API' : 'Backend API'

