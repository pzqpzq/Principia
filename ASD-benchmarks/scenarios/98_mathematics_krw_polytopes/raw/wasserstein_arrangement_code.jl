using Oscar
using Graphs
using CountingChambers

function AllCycles(G)
    DG = SimpleDiGraph(Graphs.nv(G))
    for e in Graphs.edges(G)
        Graphs.add_edge!(DG, e.dst, e.src)
        Graphs.add_edge!(DG, e.src, e.dst)
    end
    cycs = filter(k->length(k)>2,simplecycles(DG))
    return cycs
end

function WassersteinMatroid(dim, return_matroid)
    G = Graphs.complete_graph(dim)
    cyclelist = AllCycles(G) 
    evencycls = filter!(x-> length(x)% 2 == 0, cyclelist) 
    listecycles = [] 
    edgelist = collect(combinations(1:dim, 2))
    for cycle in evencycls 
        permvect = vcat([1], reverse(2:length(cycle)))
        if !(cycle[permvect] in listecycles) 
            push!(listecycles, cycle)
        end 
    end 
    mat = zeros(Int, length(edgelist), length(listecycles))
    counter = 1
    for cycle in listecycles
        paritybit = 1 
        m = length(cycle)
        for i in (1:m)
            if i < m
                pair = sort(cycle[[i,i+1]]) 
            else 
                pair = sort(cycle[[1,m]]) 
            end 
            index = findfirst(x-> x==pair , edgelist)  
            mat[index, counter] = paritybit
            paritybit = paritybit * (-1)
        end 
        counter = counter + 1
    end 
    if return_matroid
        return  [matrix(Int, mat), matroid_from_matrix_columns(matrix(QQ, mat))] 
    else 
        return mat 
    end
end 

mat5 = WassersteinMatroid(5, false)

number_of_chambers(mat5)

function KRWPolytopeMatrix(metric, n)
    mat = zeros(QQ, n*(n-1),n)
    counter = 1
    for i in combinations(1:n, 2)
        if ndims(metric) == 1
            value = metric[counter]
        elseif ndims(metric) == 2
            value = metric[i[1], i[2]]
        end
        mat[counter*2-1, i[1]] = 1//value
        mat[counter*2-1, i[2]] = -1//value
        mat[counter*2,i[1]] = -mat[counter*2-1, i[1]]
        mat[counter*2,i[2]] = -mat[counter*2-1, i[2]]
        counter = counter + 1
    end
    return mat
end

function KRWPolytopeOscar(metric, n)
    mat = KRWPolytopeMatrix(metric, n)
    return convex_hull(mat)
end

function KRWPolytopePolymake(metric, n)
    mat = KRWPolytopeMatrix(metric, n)
    m = size(mat,1)
    one_vector = ones(Int,m,1)
    mat = hcat(one_vector,mat)
    return Polymake.polytope.Polytope(POINTS=mat)
end

n = [0 1 1 1 ; 1 0 1 1 ; 1 1 0 1 ; 1 1 1 0]; 
P = KRWPolytopeOscar(n, 4)

function MetricConeMatrix(n)
    @assert n > 1
    edges = collect(combinations(1:n, 2)) 
    m = length(edges)
    mat = zeros(Int,m,m)
    for i in 1:m
        mat[i,i] = 1
    end
    S3 = symmetric_group(3)
    for tuple in combinations(1:n, 3)
        for pi in S3
            triple = [tuple[pi(i)] for i in 1:3]
            vect = repeat([0], outer = m)
            vect[findfirst(x -> x == sort([triple[1], triple[2]]), edges)] = 1 
            vect[findfirst(x -> x == sort([triple[2], triple[3]]), edges)] = 1 
            vect[findfirst(x -> x == sort([triple[1], triple[3]]), edges)] = -1 
            mat = hcat(mat, vect)
        end 
    end 
    mat = transpose(mat)
    return return mat
end 

function MetricCone(n)
    @assert n > 1
    mat = MetricConeMatrix(n)
    cone = Polymake.polytope.Cone(INEQUALITIES= mat)
    return cone
end 

function polish_metric(metric)
    oscar_metric = [QQ(d) for d in metric]
    oscar_metric = lcm([denominator(i) for i in oscar_metric])*oscar_metric
end

function get_non_isomorphic_polytopes(n, metric_list)
    polytope_list = []
    for metric in metric_list 
        push!(polytope_list, KRWPolytopePolymake(metric, n))
    end
    unique_indices = []
    for i in 1:length(metric_list)
        krw_polytope = polytope_list[i]
        unique = true
        for j in 1:length(unique_indices)
            unique_krw_polytope = polytope_list[unique_indices[j]]
            if Oscar.Polymake.polytope.isomorphic(krw_polytope, unique_krw_polytope)
                unique = false
                break 
            end
        end
        if unique
            push!(unique_indices, i)
        end 
    end
    return [(polyhedron(polytope_list[i[1]]), polish_metric(metric_list[i[1]])) for i in unique_indices]
end

function getUniqueGenericMetrics(n)
    HA = Polymake.fan.HyperplaneArrangement(
     HYPERPLANES=transpose(WassersteinMatroid(n,false)), 
     SUPPORT = MetricCone(n))
    decomp = HA.CHAMBER_DECOMPOSITION
    m = decomp.MAXIMAL_CONES
    raymatrix = decomp.RAYS
    metric_list = [] 
    println("number of chambers: ", decomp.N_MAXIMAL_CONES)
    for i in 1:size(m)[1]
        cone = Polymake.polytope.Cone(INPUT_RAYS=raymatrix[m[i,:], :])
        metric = cone.REL_INT_POINT
        push!(metric_list, metric)
    end 
    return get_non_isomorphic_polytopes(n, metric_list)
end


M4 = getUniqueGenericMetrics(4)
@time M5 = getUniqueGenericMetrics(5)

save("Polytopes_generic_metrics_5.mrdi", M5)

M5_loaded = load("Polytopes_generic_metrics_5.mrdi") 

function map_permutation_to_Starget(n, mat, sigma)
    pairs = collect(combinations(1:n,2))
    permuted_pairs = [sort([sigma(p[1]),sigma(p[2])]) for p in pairs]
    sigma_on_pairs = perm([findfirst(x -> x==p, permuted_pairs) for p in pairs])
    
    final_perm = Vector{Int}()
    all_columns = [mat[:,k] for k in 1:size(mat,2)]
    for i in 1:size(mat,2)
        permuted_column = permuted(mat[:,i], sigma_on_pairs)
        new_index = findfirst(x -> x==permuted_column, all_columns)
        if typeof(new_index) != Int
            new_index = -1*findfirst(x -> x==-1*permuted_column, all_columns)
        end
        push!(final_perm,new_index)
    end
    abs_perm = perm([abs(i) for i in final_perm])
    # we use signed permutation matrix to account for sign flips
    pmatrix = permutation_matrix(ZZ, abs_perm)
    for i in 1:size(mat,2)
        if sign(final_perm[i]) == -1
            pmatrix[i,:] = -1*pmatrix[i,:]
        end
    end
    return pmatrix
end

function symmetry_group_in_wasserstein(n, mat)
    Sn = symmetric_group(n)
    Starget = general_linear_group(size(mat,2),ZZ)
    G = gens(Sn)
    Gtarget = [map_permutation_to_Starget(n, mat, sigma) for sigma in G]
    emb = hom(Sn, Starget, G, Gtarget)
    H = emb(Sn)
    return H[1], emb
end

function matrix_act(vect, mat)
    return mat*matrix(vect)
end

function stabilizer_from_metric(n, mat, H, metric)
    sign_pattern = transpose(mat)*metric
    sign_pattern = matrix([ZZ(sign(i)) for i in sign_pattern])
    O = orbit(H, matrix_act, sign_pattern)
    println("order of the orbit ", length(O))
    return stabilizer(O)[1]
end

n = 5
H, emb = symmetry_group_in_wasserstein(n, mat5)
counter = 0
for i in 1:length(M5)
    println("index: ", i)
    println("metric: ", M5[i][2])
    stab = stabilizer_from_metric(5, mat5, H, M5[i][2])
    println("order of the stabilizer: ", order(stab))
    stab_n = preimage(emb,stab)[1]
    global counter += 120/order(stab_n)
    println("type of the stabilizer: ", describe(stab_n))
    println("generators of the stabilizer: ", gens(stab_n))
    println()
end
counter

function getUniqueNonGenericStrictMetrics(n)
    m = binomial(n,2)
    MC = MetricCone(n)
    matrix_of_metric_cone = MetricConeMatrix(n)
    HA = Polymake.fan.HyperplaneArrangement(HYPERPLANES=transpose(Matrix{Int64}(WassersteinMatroid(n,false))), 
        SUPPORT = MC);
    decomp = HA.CHAMBER_DECOMPOSITION
    Cs = decomp.CONES
    #println("done with cone decomposition")
    raymatrix = decomp.RAYS
    metriclist = [] 
    for i in 1:(decomp.FAN_DIM-1)
        for j in 1:size(Cs[i])[1]
            co = Polymake.polytope.Cone(INPUT_RAYS = raymatrix[Cs[i][j,:],:])
            metric = co.REL_INT_POINT
            # check if the metric is strict:
            vec = matrix_of_metric_cone*metric
            if all(x-> x > 0, vec)
                push!(metriclist, metric)
            end
        end 
    end
    #println("done with metrics. found ", length(metriclist), " strict metrics.")
    return get_non_isomorphic_polytopes(n, metriclist)
end

S4 = getUniqueNonGenericStrictMetrics(4) 
@time S5 = getUniqueNonGenericStrictMetrics(5)

n = 5
H, emb = symmetry_group_in_wasserstein(n, mat5)
counter = 0

sorted_collection = Dict()
# [f_vector, [(metric, group)]]
for i in 1:length(S5)
    println("index: ", i)
    println("metric: ", S5[i][2])
    fvec = f_vector(S5[i][1])
    println("f vector: ", fvec)
    
    stab = stabilizer_from_metric(5, mat5, H, S5[i][2])
    println("order of the stabilizer: ", order(stab))
    stab_n = preimage(emb,stab)[1]
    global counter += 120/order(stab_n)
    println("type of the stabilizer: ", describe(stab_n))
    println("generators of the stabilizer: ", gens(stab_n))
    println()
    if haskey(sorted_collection, fvec)
        push!(sorted_collection[fvec],(S5[i][2], describe(stab_n)))
    else
        sorted_collection[fvec] = [(S5[i][2], describe(stab_n))]
    end     
end
counter

sorted_fvecs = sort(collect(keys(sorted_collection)))
f_counter = 1
for fvec in sorted_fvecs
    println("f vector: ", Vector{Int}(fvec), " has ", length(sorted_collection[fvec]), " polytopes")
    #println(length(sorted_collection[fvec]))
    inner_counter = 1
    for i in 1:length(sorted_collection[fvec])
        current_metric, group = collect(sorted_collection[fvec])[i]
        int_metric = [Int(m) for m in current_metric]
        println("index: ", f_counter, ".", inner_counter, " metric: ", int_metric, " group: ", group )
        inner_counter += 1
    end
    println()
    f_counter += 1
end

save("Polytopes_strict_metrics_5.mrdi",S5)

load("Polytopes_strict_metrics_5.mrdi")
