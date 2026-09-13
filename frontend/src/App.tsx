import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import WorkflowListPage from "./pages/WorkflowListPage";
import CreateWorkflowPage from "./pages/CreateWorkflowPage";
import WorkflowDetailPage from "./pages/WorkflowDetailPage";
import ItemDetailPage from "./pages/ItemDetailPage";
import ModelsPage from "./pages/ModelsPage";
import ProvidersPage from "./pages/ProvidersPage";
import InfrastructurePage from "./pages/InfrastructurePage";
import Layout from "./components/Layout";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/workflows" replace />} />
          <Route path="/workflows" element={<WorkflowListPage />} />
          <Route path="/workflows/new" element={<CreateWorkflowPage />} />
          <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
          <Route path="/workflows/:wfId/items/:itemId" element={<ItemDetailPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/infra" element={<InfrastructurePage />} />
          <Route path="/infrastructure" element={<Navigate to="/infra" replace />} />
          <Route path="/worker" element={<Navigate to="/infra" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
