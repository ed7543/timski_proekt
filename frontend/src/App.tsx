import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ProtectedRoute } from './routes/ProtectedRoute';
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage';
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage';
import { ChatPage } from './pages/ChatPage';
import { JoinConversationPage } from './pages/JoinConversationPage';
import { CoursesPage } from './pages/CoursesPage';
import { MarketplacePage } from './pages/MarketplacePage';
import { CourseDetailPage } from './pages/CourseDetailPage';
import { ProgressPage } from './pages/ProgressPage';
import { AdminPage } from './pages/AdminPage';
import { MyCoursesPage } from './pages/MyCoursesPage';
import { BlogPage } from './pages/BlogPage';
import { SubscribePage } from './pages/SubscribePage';
import { SubmitCoursePage } from './pages/SubmitCoursePage';
import { BillingSuccessPage } from './pages/billing/BillingSuccessPage';
import { BillingCancelPage } from './pages/billing/BillingCancelPage';
import { NotFoundPage } from './pages/NotFoundPage';

function RootRedirect() {
  const { status } = useAuth();
  if (status === 'loading') return null;
  return <Navigate to={status === 'authenticated' ? '/chat' : '/login'} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<RootRedirect />} />

            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/chat/join/:token" element={<JoinConversationPage />} />
            {/* Public, matching the backend (GET /api/blog requires no auth,
                see routes/blogRoute.py) - BlogPage itself already hides the
                admin-only add/delete controls behind user?.role === 'admin',
                so there's nothing here that needs a logged-in visitor. */}
            <Route path="/blog" element={<BlogPage />} />

            <Route element={<ProtectedRoute />}>
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/chat/:conversationId" element={<ChatPage />} />
              <Route path="/courses" element={<CoursesPage />} />
              <Route path="/courses/:courseId" element={<CourseDetailPage />} />
              <Route path="/marketplace" element={<MarketplacePage />} />
              <Route path="/marketplace/submit" element={<SubmitCoursePage />} />
              <Route path="/marketplace/:courseId" element={<CourseDetailPage />} />
              <Route path="/billing/success" element={<BillingSuccessPage />} />
              <Route path="/billing/cancel" element={<BillingCancelPage />} />
              <Route path="/progress" element={<ProgressPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/my-courses" element={<MyCoursesPage />} />
              <Route path="/subscribe" element={<SubscribePage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}

export default App;
