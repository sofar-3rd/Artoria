import { useRoute } from './router'
import ChatPage from './ChatPage'
import TraceDetailPage from './pages/TraceDetailPage'
import TracesPage from './pages/TracesPage'

export default function App() {
  const route = useRoute()
  switch (route.page) {
    case 'traces':
      return <TracesPage key={route.threadId ?? ''} threadId={route.threadId} />
    case 'trace':
      return <TraceDetailPage key={route.id} id={route.id} />
    default:
      return <ChatPage />
  }
}
