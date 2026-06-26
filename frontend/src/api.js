import axios from "axios";
import { getToken } from "./auth";

const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use((config) => {
  const token = getToken();

  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export function getHealth() {
  return api.get("/health");
}

export function getPosts() {
  return api.get("/posts");
}

export function getPost(id) {
  return api.get(`/posts/${id}`);
}

export function createPost(payload) {
  return api.post("/posts", payload);
}

export function getComments(postId) {
  return api.get(`/posts/${postId}/comments`);
}

export function createComment(postId, payload) {
  return api.post(`/posts/${postId}/comments`, payload);
}

export function login(payload) {
  return api.post("/auth/login", payload);
}

export function register(payload) {
  return api.post("/auth/register", payload);
}
