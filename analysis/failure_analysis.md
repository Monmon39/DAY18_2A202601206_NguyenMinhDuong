# Failure Analysis - Lab 18: Production RAG

**Nhóm:** Cá nhân  
**Thành viên:** Nguyễn Minh Dương - implement M1, M2, M3, M4, M5

## RAGAS Scores

| Metric | Naive Baseline | Production | Delta |
|--------|---------------:|-----------:|------:|
| Faithfulness | 1.0000 | 1.0000 | +0.0000 |
| Answer Relevancy | 0.7628 | 0.7094 | -0.0534 |
| Context Precision | 0.2193 | 0.2135 | -0.0058 |
| Context Recall | 0.8601 | 0.8235 | -0.0366 |

## Bottom-5 Failures

### #1
- **Question:** Muốn mua thiết bị trị giá 55 triệu cần ai phê duyệt?
- **Expected:** Đơn hàng trên 50.000.000 VNĐ cần Tổng Giám đốc (CEO) phê duyệt.
- **Got:** Chunk trả về nội dung lưu ý mua sắm thiết bị CNTT, nhưng thiếu dòng quy định ngưỡng phê duyệt trên 50 triệu.
- **Worst metric:** context_precision
- **Error Tree:** Output sai một phần -> Context có liên quan nhưng chưa đúng điểm cần tìm -> Query bị hút về “thiết bị CNTT” hơn là “55 triệu/phê duyệt”.
- **Root cause:** Ranking lexical ưu tiên chunk có cụm “thiết bị CNTT” thay vì chunk có bảng ngưỡng tiền phê duyệt.
- **Suggested fix:** Thêm metadata `category=procurement`, ưu tiên numeric/range matching và rerank theo ngưỡng tiền.

### #2
- **Question:** Cần mua laptop 30 triệu cho nhân viên mới, ai phê duyệt và cần gì từ phòng CNTT?
- **Expected:** Director phê duyệt, cần xác nhận cấu hình kỹ thuật từ CNTT, kèm ít nhất 3 báo giá.
- **Got:** Chunk đào tạo 30 triệu bị lấy nhầm vì trùng số 30.000.000.
- **Worst metric:** context_precision
- **Error Tree:** Output sai -> Context sai domain -> Query multi-hop chưa tách điều kiện laptop + 30 triệu + CNTT.
- **Root cause:** Numeric overlap làm retrieval nhầm sang chính sách hoàn chi đào tạo.
- **Suggested fix:** Query rewrite thành các sub-query: mua sắm laptop, ngưỡng 5-50 triệu, xác nhận CNTT.

### #3
- **Question:** Senior có 9 năm thâm niên được nghỉ bao nhiêu ngày phép năm và lương trong khoảng nào?
- **Expected:** 18 ngày phép; lương Senior P3-P4 là 20-35 triệu VNĐ/tháng.
- **Got:** Chunk chính sách nghỉ phép 2023, thiếu bảng lương Senior.
- **Worst metric:** context_precision
- **Error Tree:** Output thiếu -> Context chỉ đúng một phần -> Query multi-hop cần ghép nghỉ phép v2024 + bảng lương.
- **Root cause:** Retrieval top-3 chưa bao phủ đủ hai tài liệu cần thiết.
- **Suggested fix:** Tăng recall theo sub-query và gom context theo parent document.

### #4
- **Question:** Lương thử việc của nhân viên Junior mức cao nhất là bao nhiêu?
- **Expected:** 85% x 20.000.000 = 17.000.000 VNĐ/tháng.
- **Got:** Context có công thức 85% nhưng thiếu mức lương Junior cao nhất.
- **Worst metric:** context_precision
- **Error Tree:** Output thiếu tính toán -> Context thiếu bảng lương -> Query cần numeric reasoning.
- **Root cause:** Reranker local ưu tiên chunk thử việc hơn chunk `bang_luong_2024`.
- **Suggested fix:** Lấy thêm context từ bảng lương khi query có “Junior” và “cao nhất”.

### #5
- **Question:** Bao lâu phải đổi mật khẩu một lần?
- **Expected:** Theo v2.0 hiện hành là 120 ngày; v1.0 là 90 ngày nhưng đã bị thay thế.
- **Got:** Chunk v1.0 với chu kỳ 90 ngày đứng đầu, chunk v2.0 nằm ở context sau.
- **Worst metric:** context_precision
- **Error Tree:** Output sai version -> Context có cả bản cũ và bản mới -> Ranking không ưu tiên version hiện hành.
- **Root cause:** Chưa có metadata/version filter và chưa boost các tín hiệu như “hiện hành”, “đã thay thế”.
- **Suggested fix:** Extract metadata `version/status`, filter bỏ tài liệu cũ khi câu hỏi hỏi chính sách hiện hành.

## Case Study

**Question chọn phân tích:** Bao lâu phải đổi mật khẩu một lần?

**Error Tree walkthrough:**
1. Output đúng? -> Chưa đúng, trả 90 ngày thay vì 120 ngày.
2. Context đúng? -> Có cả v1.0 và v2.0, nhưng v1.0 đứng đầu.
3. Query rewrite OK? -> Chưa, cần thêm ý “chính sách hiện hành”.
4. Fix ở bước: Retrieval/reranking bằng metadata version.

**Nếu có thêm 1 giờ, sẽ optimize:**
- Thêm metadata `version`, `effective_date`, `status`.
- Boost tài liệu có “hiện hành”, “v2.0”, “đã thay thế”.
- Tách query multi-hop thành nhiều truy vấn nhỏ rồi hợp nhất context.
