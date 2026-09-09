import '@/lib/extensions'; // Import all global extensions
import { HashRouter as Router, Routes, Route, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/stores/state'
import { navigationService } from '@/services/navigation'
import { Toaster } from 'sonner'
import App from './App'
import GraphEmbedApp from '@/features/GraphEmbedApp'
import LoginPage from '@/features/LoginPage'
import ThemeProvider from '@/components/ThemeProvider'

const AppContent = () => {
  const [initializing, setInitializing] = useState(true)
  const { isAuthenticated } = useAuthStore()
  const navigate = useNavigate()

  // Set navigate function for navigation service
  useEffect(() => {
    navigationService.setNavigate(navigate)
  }, [navigate])

  // Token validity check
  useEffect(() => {

    const checkAuth = async () => {
      try {
        const token = localStorage.getItem('LIGHTRAG-API-TOKEN')

        if (token && isAuthenticated) {
          setInitializing(false);
          return;
        }

        if (!token) {
          useAuthStore.getState().logout()
        }
      } catch (error) {
        console.error('Auth initialization error:', error)
        if (!isAuthenticated) {
          useAuthStore.getState().logout()
        }
      } finally {
        setInitializing(false)
      }
    }

    checkAuth()

    return () => {
    }
  }, [isAuthenticated])

  // Redirect effect for protected routes
  useEffect(() => {
    if (!initializing && !isAuthenticated) {
      const currentPath = window.location.hash.slice(1).split('?')[0];
      if (currentPath !== '/login' && !currentPath.startsWith('/embed/')) {
        console.log('Not authenticated, redirecting to login');
        navigate('/login');
      }
    }
  }, [initializing, isAuthenticated, navigate]);

  // Show loading indicator while initializing auth
  if (initializing) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <div className="text-center">
          <div className="border-primary mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" />
          <p className="text-muted-foreground text-sm">Loading…</p>
        </div>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/embed/graph" element={<GraphEmbedApp />} />
      <Route
        path="/*"
        element={
          isAuthenticated ? (
            <App />
          ) : (
            <div className="flex h-screen w-screen items-center justify-center">
              <div className="border-primary h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" />
            </div>
          )
        }
      />
    </Routes>
  )
}

const AppRouter = () => {
  return (
    <ThemeProvider>
      <Router>
        <AppContent />
        <Toaster
          position="bottom-center"
          theme="system"
          closeButton
          richColors
        />
      </Router>
    </ThemeProvider>
  )
}

export default AppRouter
