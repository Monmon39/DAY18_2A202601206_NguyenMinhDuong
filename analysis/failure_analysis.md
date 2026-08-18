# Failure Analysis - Lab 18: Production RAG

**Nhom:** Ca nhan  
**Thanh vien:** Nguyen Minh Duong - implement M1, M2, M3, M4, M5

## RAGAS Scores

| Metric | Naive Baseline | Production | Delta |
|--------|---------------:|-----------:|------:|
| Faithfulness | 1.0000 | 1.0000 | +0.0000 |
| Answer Relevancy | 0.7628 | 0.7094 | -0.0534 |
| Context Precision | 0.2193 | 0.2135 | -0.0058 |
| Context Recall | 0.8601 | 0.8235 | -0.0366 |

## Bottom-5 Failures

### #1
- **Question:** Muon mua thiet bi tri gia 55 trieu can ai phe duyet?
- **Expected:** Don hang tren 50.000.000 VND can Tong Giam doc (CEO) phe duyet.
- **Got:** Chunk tra ve noi dung luu y mua sam thiet bi CNTT, nhung thieu dong nguong phe duyet tren 50 trieu.
- **Worst metric:** context_precision
- **Error Tree:** Output sai mot phan -> Context co lien quan nhung chua dung diem -> Query bi hut ve "thiet bi CNTT" hon la "55 trieu/phe duyet".
- **Root cause:** Ranking lexical uu tien chunk co cum "thiet bi CNTT" thay vi chunk co bang nguong tien phe duyet.
- **Suggested fix:** Them metadata category=procurement, uu tien numeric/range matching va rerank theo nguong tien.

### #2
- **Question:** Can mua laptop 30 trieu cho nhan vien moi, ai phe duyet va can gi tu phong CNTT?
- **Expected:** Director phe duyet, can xac nhan cau hinh ky thuat tu CNTT, kem it nhat 3 bao gia.
- **Got:** Chunk dao tao 30 trieu bi lay nham vi trung so 30.000.000.
- **Worst metric:** context_precision
- **Error Tree:** Output sai -> Context sai domain -> Query multi-hop chua tach dieu kien laptop + 30 trieu + CNTT.
- **Root cause:** Numeric overlap lam retrieval nham sang hoan chi dao tao.
- **Suggested fix:** Query rewrite thanh cac sub-query: mua sam laptop, nguong 5-50 trieu, xac nhan CNTT.

### #3
- **Question:** Senior co 9 nam tham nien duoc nghi bao nhieu ngay phep nam va luong trong khoang nao?
- **Expected:** 18 ngay phep; luong Senior P3-P4 la 20-35 trieu VND/thang.
- **Got:** Chunk chinh sach nghi phep 2023, thieu bang luong Senior.
- **Worst metric:** context_precision
- **Error Tree:** Output thieu -> Context chi dung mot phan -> Query multi-hop can ghep nghi phep v2024 + bang luong.
- **Root cause:** Retrieval top-3 chua bao phu du hai tai lieu can thiet.
- **Suggested fix:** Tang recall theo sub-query va gom context theo parent document.

### #4
- **Question:** Luong thu viec cua nhan vien Junior muc cao nhat la bao nhieu?
- **Expected:** 85% x 20.000.000 = 17.000.000 VND/thang.
- **Got:** Context co cong thuc 85% nhung thieu muc luong Junior cao nhat.
- **Worst metric:** context_precision
- **Error Tree:** Output thieu tinh toan -> Context thieu bang luong -> Query can numeric reasoning.
- **Root cause:** Reranker local uu tien chunk thu viec hon chunk bang_luong_2024.
- **Suggested fix:** Lay them context tu bang luong khi query co "Junior" va "cao nhat".

### #5
- **Question:** Bao lau phai doi mat khau mot lan?
- **Expected:** Theo v2.0 hien hanh la 120 ngay; v1.0 90 ngay da bi thay the.
- **Got:** Chunk v1.0 90 ngay dung dau, chunk v2.0 nam o context sau.
- **Worst metric:** context_precision
- **Error Tree:** Output sai version -> Context co ca cu va moi -> Ranking khong uu tien version hien hanh.
- **Root cause:** Chua co metadata/version filter va chua boost "hien hanh", "da thay the".
- **Suggested fix:** Extract metadata version/status, filter bo tai lieu old khi cau hoi hoi chinh sach hien hanh.

## Case Study

**Question chon phan tich:** Bao lau phai doi mat khau mot lan?

**Error Tree walkthrough:**
1. Output dung? -> Chua dung, tra 90 ngay thay vi 120 ngay.
2. Context dung? -> Co ca v1.0 va v2.0, nhung v1.0 dung dau.
3. Query rewrite OK? -> Chua, can them y "chinh sach hien hanh".
4. Fix o buoc: Retrieval/reranking bang metadata version.

**Neu co them 1 gio, se optimize:**
- Them metadata `version`, `effective_date`, `status`.
- Boost tai lieu co "hien hanh", "v2.0", "thay the".
- Tach query multi-hop thanh nhieu truy van nho roi hop nhat context.
