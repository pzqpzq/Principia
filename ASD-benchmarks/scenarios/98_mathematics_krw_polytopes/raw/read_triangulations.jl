using Oscar

function KRWPolytope(A::Matrix)
    @assert size(A,1) == size(A,2)
    n = size(A,1)

    Points = zeros(Int, n, n*(n-1))
    Points = matrix(QQ,Points)
    column_counter=1
    for i in 1:n
        for j in 1:n
            if i != j
                @assert A[i,j] != 0
                @assert A[i,j] == A[j,i]
                Points[i,column_counter] = 1//A[i,j]
                Points[j,column_counter] = -1//A[i,j]
                column_counter += 1
            end
        end
    end
    P = convex_hull(transpose(Points))
    return P
end

root_poly_4 = 
transpose([1	-1	1	-1	1	-1	0	0	0	0	0	0	0;
-1	1	0	0	0	0	1	-1	1	-1	0	0	0;	
0	0	-1	1	0	0	-1	1	0	0	1	-1	0;	
0	0	0	0	-1	1	0	0	-1	1	-1	1	0])

root_poly_5 = transpose([1	-1	1	-1	1	-1	1	-1	0	0	0	0	0	0	0	0	0	0	0	0	0;
-1	1	0	0	0	0	0	0	1	-1	1	-1	1	-1	0	0	0	0	0	0	0;
0	0	-1	1	0	0	0	0	-1	1	0	0	0	0	1	-1	1	-1	0	0	0;
0	0	0	0	-1	1	0	0	0	0	-1	1	0	0	-1	1	0	0	1	-1	0;
0	0	0	0	0	0	-1	1	0	0	0	0	-1	1	0	0	-1	1	-1	1	0]);

root_poly_6 = transpose([1	-1	1	-1	1	-1	1	-1	1	-1	0	0	0	0	0	0	0	0	0	0	0	0	0	0	0	0	0 0	0	0	0;
-1	1	0	0	0	0	0	0	0	0	1	-1	1	-1	1	-1	1	-1	0	0	0	0	0	0	0	0	0	0	0	0	0;
0	0	-1	1	0	0	0	0	0	0	-1	1	0	0	0	0	0	0	1	-1	1	-1	1	-1	0	0	0	0	0	0	0;
0	0	0	0	-1	1	0	0	0	0	0	0	-1	1	0	0	0	0	-1	1	0	0	0	0	1	-1	1	-1	0	0	0;
0	0	0	0	0	0	-1	1	0	0	0	0	0	0	-1	1	0	0	0	0	-1	1	0	0	-1	1	0	0	1	-1	0;
0	0	0	0	0	0	0	0	-1	1	0	0	0	0	0	0	-1	1	0	0	0	0	-1	1	0	0	-1	1	-1	1	0]);

root_polys = [0,0,0,root_poly_4,root_poly_5,root_poly_6]

point2metric = function(n, f)
    A = zeros(QQ,n,n)
    for i in 1:length(f)-1
       if i%2 == 1
            if n == 4
                v = root_poly_4[i,:]
            elseif n == 5
                v = root_poly_5[i,:]
            elseif n == 6
                v = root_poly_6[i,:]
            else
                error("not supported n")
            end
            j = findfirst(i->i==1, v)
            k = findfirst(i->i==-1, v)
            A[j,k] = f[i]
            A[k,j] = f[i]
        end
    end
    return A
end

# Constructs the cone that ensures that ij = ji
function symmetry_cone(n)
    A = zeros(Int,binomial(n,2),2*binomial(n,2)+1)
    for i in 1:binomial(n,2)
        A[i,2*i-1]=1
        A[i,2*i]=-1
    end
    C = cone_from_equations(A)
    return C
end

# Constructs the cone that ensures that ij => 0
function positivity_cone(n)
    A = zeros(Int,binomial(n,2),2*binomial(n,2)+1)
    for i in 1:binomial(n,2)
        A[i,2*i-1]=-1
    end
    C = cone_from_inequalities(A)
    return C
end

function find_root(n,i,j)
    e = zeros(Int,n)
    e[i] = 1
    e[j] = -1
    for k in 1:size(root_polys[n],1)
        if e == root_polys[n][k,:]
            return k
        end
    end
    error("Root not found")
end

# Constructs the cone that ensures the triangle inequalities
function triangular_cone(n)
    # This should give the conditions ij + jk \ge ik
    A = zeros(Int,binomial(n,3)*factorial(3),2*binomial(n,2)+1)
    counter = 1
    for i in 1:n
        for j in 1:n
            for k in 1:n
                if length(Set([i,j,k])) < 3
                    continue
                end
                ijrp = find_root(n,i,j)
                jkrp = find_root(n,j,k)
                ikrp = find_root(n,i,k)
                A[counter,ijrp] = -1
                A[counter,jkrp] = -1
                A[counter,ikrp] = 1
                counter += 1
            end
        end
    end
    return cone_from_inequalities(A)
end

# Constructs the metric cone as the intersection of the above cones
function metric_cone(n)
    C = symmetry_cone(n)
    C = intersect(C,positivity_cone(n))
    C = intersect(C,triangular_cone(n))
    return C
end

# Reads on triangulation and outputs the corresponding polytope, metric and f-vector
function read_triangulation(triangulation, n)
    IM = IncidenceMatrix([[i+1 for i in s] for s in triangulation])
    SOP = subdivision_of_points(root_polys[n], IM)
    SC = secondary_cone(SOP)

    SSC = intersect(SC,metric_cone(n))
    f = relative_interior_point(SSC)
    f = lcm([denominator(f[i]) for i in 1:length(f)]) * f
    met = point2metric(n,f)

    P = KRWPolytope(met)
    @assert is_simplicial(P)

    result = (P, [Int(i) for i in met])
    return result
end

# This function reads all triangulations from a file in which each line is a triangulation
# If a start or end index is given, only the lines in that range are read from the file
function read_triangulations_from_file(file_name, n, startind=nothing::Union{Int,Nothing},endind=nothing::Union{Int,Nothing})
    @assert 4 <= n && n <= 6
    counter = 0
    collection = []
    for s in eachline(file_name)
        counter += 1
        if startind != nothing && counter < startind
            continue
        end
        if endind != nothing && counter > endind
            break
        end

        while s[length(s)] == ','
            s = chop(s, tail=1)
        end
        triangulation = [[]]
        try
            triangulation = eval(Meta.parse(s))
        catch
            println("wrong parsing in line ", counter)
            error("fail")
        end
        P, metric = read_triangulation(triangulation, n)
        push!(collection, (P, metric))
        
        if counter % 500 == 0
            println("Done with ", counter, " triangulations.")
        end
    end
    return collection
end

# read_triangulations_from_file("triangulations_4.jl",4)
# T5 = read_triangulations_from_file("triangulations_5.jl",5)
# The file with 6 triangulations is rather large and therefore best read in pieces in OSCAR
# T6 = read_triangulations_from_file("triangulations_6.jl",6,)