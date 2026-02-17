import numpy as np
from scipy.linalg import eigh, svd
from datetime import datetime
from typing import Tuple, List


def hub_detection(W: np.ndarray, k: int, hub: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hub detection for a single network.
    
    Args:
        W: connectivity matrix (n_nodes, n_nodes)
        k: embedding dimension
        hub: predefined number of hubs
        
    Returns:
        F: embedding matrix
        S: selection matrix (diagonal entries of 0 indicate hubs)
    """
    n_nodes = W.shape[0]
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBSINGLE] Starting hub detection (n_nodes={n_nodes}, k={k}, hub={hub})")
    
    # Compute the degree matrix.
    d = np.sum(W, axis=1)
    D = np.diag(d)
    
    # Initialize variables.
    s = np.ones(n_nodes)
    S = np.diag(s)
    A = np.zeros((n_nodes, n_nodes))
    Lamda = np.ones(n_nodes)
    I = np.ones(n_nodes)
    
    max_iter = 500
    sub_iter = 20
    mu = 10.0
    rho = 1.2
    iter_count = 1
    cost = [1e10]
    s_old = np.zeros(n_nodes)
    se_old = 1e10
    
    # Initialize F using Laplacian eigenvectors.
    L = D - W
    eigenvalues, eigenvectors = eigh(L)
    idx = np.argsort(eigenvalues)
    
    # Check for near-zero eigenvalues.
    zero_indices = np.where(eigenvalues < 1e-10)[0]
    if len(zero_indices) == 0:
        F = eigenvectors[:, idx[:k]]
    else:
        ad_cont = len(zero_indices)
        F = eigenvectors[:, idx[:(k + ad_cont)]]
    
    # Main optimization loop.
    while True:
        # Compute A matrix.
        for i in range(n_nodes):
            F_diff = F[i, :] - F  # (n_nodes, k)
            A[:, i] = W[:, i] * np.sum(F_diff ** 2, axis=1)
        
        # Update S (subproblem).
        temp_mu = mu
        for _ in range(sub_iter):
            # Update p.
            temp = Lamda - A.T @ s
            p = s + (1.0 / temp_mu) * temp
            
            # Compute e.
            e = (A - temp_mu * np.outer(I, I)) @ p + Lamda + (temp_mu / 2.0) * I
            
            # Sort to find hubs.
            loc = np.argsort(e)[::-1]  # 降序
            
            # Update s (set the top "hub" indices to 0, indicating hubs).
            s = np.ones(n_nodes)
            s[loc[:hub]] = 0
            
            se = s @ e
            dif_s = s_old - s
            
            if np.sum(np.abs(dif_s)) <= 0 or se >= se_old or np.abs(se - se_old) / np.abs(se) < 1e-6:
                break
            
            s_old = s.copy()
            se_old = se
            temp_mu = min(1e10, temp_mu * rho)
        
        S = np.diag(s_old)
        Lamda = Lamda + mu * (s - p)
        mu = min(1e10, mu * rho)
        
        # Compute cost.
        old_cost = cost[iter_count - 1]
        iter_count += 1
        
        # Update F by recomputing eigenvectors.
        D_new = np.diag(np.sum(S.T @ W @ S, axis=1))
        L_new = D_new - S.T @ W @ S
        
        eigenvalues, eigenvectors = eigh(L_new)
        idx = np.argsort(eigenvalues)
        
        zero_indices = np.where(eigenvalues < 1e-10)[0]
        if len(zero_indices) == 0:
            F = eigenvectors[:, idx[:k]]
        else:
            ad_cont = len(zero_indices)
            F = eigenvectors[:, idx[:(k + ad_cont)]]
        
        new_cost = np.trace(F.T @ (D_new - S.T @ W @ S) @ F)
        cost.append(new_cost)
        
        # Check convergence.
        if (np.abs(old_cost - new_cost) / np.abs(new_cost) < 1e-6 or 
            iter_count > max_iter or 
            np.abs(old_cost - new_cost) < 1e-6):
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBSINGLE]   Iteration {iter_count}: cost={new_cost:.6f} (converged)")
            break
        else:
            if iter_count % 50 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBSINGLE]   Iteration {iter_count}/{max_iter}: cost={new_cost:.6f}")
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBSINGLE] Hub detection complete (iterations={iter_count})")
    return F, S


def hub_detection_grassmannifold(Wn: np.ndarray, k: int, hub: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hub detection for multiple networks (Grassmann manifold method).
    
    Args:
        Wn: connectivity matrix set (n_nodes, n_nodes, n_subjects)
        k: embedding dimension
        hub: predefined number of hubs
        
    Returns:
        Fn: embedding matrices (n_nodes, k, n_subjects)
        S: selection matrix (diagonal entries of 0 indicate hubs)
    """
    n_nodes, _, n_subjects = Wn.shape
    M = n_subjects
    alpha = 1.0 / M
    beta = 0.1 * alpha
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBGROUP] Starting group hub detection (n_subjects={n_subjects}, n_nodes={n_nodes}, k={k}, hub={hub})")
    
    # Compute degree matrices.
    Dn = np.zeros_like(Wn)
    for i in range(n_subjects):
        W = Wn[:, :, i]
        d = np.sum(W, axis=1)
        Dn[:, :, i] = np.diag(d)
    
    # Initialize variables.
    s = np.ones(n_nodes)
    S = np.diag(s)
    Lamda = np.ones(n_nodes)
    I = np.ones(n_nodes)
    
    max_iter = 500
    sub_iter = 20
    iternum = 200
    mu = 10.0
    rho = 1.2
    iter_count = 1
    cost = [1e10]
    s_old = np.zeros(n_nodes)
    se_old = 1e10
    
    Im = np.eye(n_nodes)
    
    # Initialize Fn.
    Ln = Dn - Wn
    Fn = np.zeros((n_nodes, k, n_subjects))
    for i in range(n_subjects):
        L = Ln[:, :, i]
        eigenvalues, eigenvectors = eigh(L)
        idx = np.argsort(eigenvalues)
        Fn[:, :, i] = eigenvectors[:, idx[:k]]
    
    # Main optimization loop.
    while True:
        # Update F (Grassmann optimization).
        for j in range(n_subjects):
            W = Wn[:, :, j]
            D = np.diag(np.sum(S.T @ W @ S, axis=1))
            L = D - S.T @ W @ S
            Ln[:, :, j] = L
        
        tempFn = np.zeros_like(Fn)
        for i in range(n_subjects):
            Fi = Fn[:, :, i]
            Li = Ln[:, :, i]
            
            t = 0.5
            ts = 0.9
            
            for iteration in range(iternum):
                # Compute Grassmann gradient.
                temp_dist = np.zeros((n_nodes, k))
                for j in range(n_subjects):
                    Fj = Fn[:, :, j]
                    temp_dist -= alpha * (Im - Fi @ Fi.T) @ Fj @ Fj.T @ Fi
                
                grassmann_gradient = beta * (Li @ Fi - Fi @ (Fi.T @ Li @ Fi)) + temp_dist
                
                # Update via SVD.
                U, sigma, Vt = svd(-grassmann_gradient, full_matrices=False)
                V = Vt.T

                # MATLAB: UV is diagonal matrix of singular values
                # Python: s is a vector -> construct Σ
                cos_S = np.diag(np.cos(sigma * t))
                sin_S = np.diag(np.sin(sigma * t))

                # MATLAB: Fi = (Fi * V * cos_uv + U * sin_uv) * V'
                Fi = Fi @ V @ cos_S @ V.T + U @ sin_S @ V.T
                t = t * ts
                
                # Check convergence.
                distfi = np.sqrt(np.sum((-Fi.T @ grassmann_gradient) ** 2))
                if distfi < 1e-2:
                    break
            
            tempFn[:, :, i] = Fi
        
        Fn = tempFn
        
        # Update S.
        An = np.zeros_like(Wn)
        for j in range(n_subjects):
            W = Wn[:, :, j]
            F = Fn[:, :, j]
            
            tempA = np.zeros((n_nodes, n_nodes))
            for i in range(n_nodes):
                F_diff = F[i, :] - F
                tempA[:, i] = W[:, i] * np.sum(F_diff ** 2, axis=1) / n_subjects
            
            An[:, :, j] = tempA
        
        A = np.sum(An, axis=2) / M
        
        # Update s (subproblem).
        temp_mu = mu
        for _ in range(sub_iter):
            temp = Lamda - A.T @ s
            p = s + (1.0 / temp_mu) * temp
            e = (A - temp_mu * np.outer(I, I)) @ p + Lamda + (temp_mu / 2.0) * I
            
            loc = np.argsort(e)[::-1]
            
            s = np.ones(n_nodes)
            s[loc[:hub]] = 0
            
            se = s @ e
            dif_s = s_old - s
            
            if np.sum(np.abs(dif_s)) <= 0 or se >= se_old or np.abs(se - se_old) / np.abs(se) < 1e-6:
                break
            
            s_old = s.copy()
            se_old = se
            temp_mu = min(1e10, temp_mu * rho)
        
        S = np.diag(s_old)
        Lamda = Lamda + mu * (s - p)
        mu = min(1e10, mu * rho)
        
        # Compute cost.
        old_cost = cost[iter_count - 1]
        iter_count += 1
        
        tempcost = 0.0
        for i in range(n_subjects):
            Fi = Fn[:, :, i]
            tempterm = 0.0
            
            for j in range(n_subjects):
                if i == j:
                    continue
                Fj = Fn[:, :, j]
                tempterm += k - np.trace(Fi @ Fi.T @ Fj @ Fj.T)
            
            tempcost += beta * np.trace(Fi.T @ Ln[:, :, i] @ Fi) + tempterm * alpha
        
        cost.append(tempcost)
        
        # Check convergence.
        if (np.abs(old_cost - cost[iter_count - 1]) / np.abs(cost[iter_count - 1]) < 1e-3 or
            iter_count > max_iter or
            np.abs(old_cost - cost[iter_count - 1]) < 1e-3):
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBGROUP]   Iteration {iter_count}: cost={tempcost:.6f} (converged)")
            break
        else:
            if iter_count % 20 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBGROUP]   Iteration {iter_count}/{max_iter}: cost={tempcost:.6f}")
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBGROUP] Group hub detection complete (iterations={iter_count})")
    return Fn, S


def detect_hubs_from_graphs(graphs: List[np.ndarray], k: int = 2, hub: int = 1, 
                            use_group: bool = False) -> dict:
    """
    Detect hubs from a list of graphs.
    
    Args:
        graphs: list of graphs, each is an adjacency matrix
        k: embedding dimension
        hub: number of hubs
        use_group: whether to use the group method
        
    Returns:
        Result dictionary containing hub nodes and embeddings
    """
    num_graphs = len(graphs)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT] Starting hub detection for {num_graphs} graph(s)...")
    
    if use_group and len(graphs) > 1:
        # Group method for multiple networks.
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT] Using group (Grassmann manifold) method")
        Wn = np.stack(graphs, axis=2)
        Fn, S = hub_detection_grassmannifold(Wn, k, hub)
        
        # Find hub nodes.
        hub_nodes = np.where(np.diag(S) == 0)[0].tolist()
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT] Hub detection complete: {len(hub_nodes)} hubs identified")
        
        return {
            "method": "group",
            "hub_nodes": hub_nodes,
            "embeddings": Fn.tolist(),
            "selection_matrix": S.tolist()
        }
    else:
        # Single-network method.
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT] Using individual (per-network) method")
        results = []
        for i, W in enumerate(graphs):
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT]   Processing graph {i+1}/{num_graphs}...")
            F, S = hub_detection(W, k, hub)
            hub_nodes = np.where(np.diag(S) == 0)[0].tolist()
            results.append({
                "graph_index": i,
                "hub_nodes": hub_nodes,
                "embedding": F.tolist(),
                "selection_matrix": S.tolist()
            })
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT]   Graph {i+1}/{num_graphs}: {len(hub_nodes)} hubs identified ✓")
        
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUBDETECT] Hub detection complete: {num_graphs} graph(s) processed")
        return {
            "method": "individual",
            "results": results
        }
