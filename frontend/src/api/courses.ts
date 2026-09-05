import { apiFetch } from './client';
import type {
  CourseOut,
  CourseDetailOut,
  CourseMaterialOut,
  RecordingOut,
  LessonOut,
  LessonDetailOut,
} from '../types/course';

export function listCourses(params?: { semester?: string; search?: string }): Promise<CourseOut[]> {
  const qs = new URLSearchParams();
  if (params?.semester) qs.set('semester', params.semester);
  if (params?.search) qs.set('search', params.search);
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<CourseOut[]>(`/api/courses${suffix}`);
}

export function getCourse(id: number): Promise<CourseDetailOut> {
  return apiFetch<CourseDetailOut>(`/api/courses/${id}`);
}

export function getCourseMaterials(id: number): Promise<CourseMaterialOut[]> {
  return apiFetch<CourseMaterialOut[]>(`/api/courses/${id}/materials`);
}

export function getCourseRecordings(id: number, category?: string): Promise<RecordingOut[]> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : '';
  return apiFetch<RecordingOut[]>(`/api/courses/${id}/recordings${qs}`);
}

export function getCourseLessons(id: number): Promise<LessonOut[]> {
  return apiFetch<LessonOut[]>(`/api/courses/${id}/lessons`);
}

export function getLesson(courseId: number, lessonId: number): Promise<LessonDetailOut> {
  return apiFetch<LessonDetailOut>(`/api/courses/${courseId}/lessons/${lessonId}`);
}

export function generateLessonQuiz(courseId: number, lessonId: number): Promise<LessonDetailOut> {
  return apiFetch<LessonDetailOut>(`/api/courses/${courseId}/lessons/${lessonId}/quiz`, {
    method: 'POST',
  });
}
