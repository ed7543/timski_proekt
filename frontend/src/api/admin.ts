import { apiFetch } from './client';
import type { AdminCourseOut, CourseModerationStatus } from '../types/course';

/** Admin-only: courses submitted by professors that are still awaiting a decision. */
export function listPendingCourses(): Promise<AdminCourseOut[]> {
  return apiFetch<AdminCourseOut[]>('/api/admin/courses/pending');
}

/** Admin-only: every user-submitted course, optionally filtered by status
 * ('pending' | 'approved' | 'rejected' | 'all'). Powers the Admin panel's
 * status tabs so approved/rejected courses have somewhere to be deleted from. */
export function listAllCourses(status: CourseModerationStatus | 'all' = 'all'): Promise<AdminCourseOut[]> {
  return apiFetch<AdminCourseOut[]>(`/api/admin/courses?status=${status}`);
}

export function approveCourse(courseId: number): Promise<AdminCourseOut> {
  return apiFetch<AdminCourseOut>(`/api/admin/courses/${courseId}/approve`, { method: 'POST' });
}

export function rejectCourse(courseId: number, reason: string): Promise<AdminCourseOut> {
  return apiFetch<AdminCourseOut>(`/api/admin/courses/${courseId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}
