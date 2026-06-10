import * as mockApi from './mockApi'
import * as httpApi from './httpApi'

const useMock = import.meta.env.VITE_USE_MOCK_API === 'true'

export const createTask = useMock ? mockApi.createTask : httpApi.createTask
export const getTask = useMock ? mockApi.getTask : httpApi.getTask
export const listTasks = useMock ? mockApi.listTasks : httpApi.listTasks
export const uploadTaskDocument = useMock
  ? mockApi.uploadTaskDocument
  : httpApi.uploadTaskDocument
export const submitClarification = useMock
  ? mockApi.submitClarification
  : httpApi.submitClarification
export const generateOutline = useMock
  ? mockApi.generateOutline
  : httpApi.generateOutline
export const generateSkeleton = useMock
  ? mockApi.generateSkeleton
  : httpApi.generateSkeleton
export const updateSkeleton = useMock
  ? mockApi.updateSkeleton
  : httpApi.updateSkeleton
export const generateSlides = useMock
  ? mockApi.generateSlides
  : httpApi.generateSlides
export const saveOutline = useMock
  ? mockApi.saveOutline
  : httpApi.saveOutline
export const regenerateSlide = useMock
  ? mockApi.regenerateSlide
  : httpApi.regenerateSlide

export const apiModeLabel = useMock ? 'Mock API' : 'Backend API'
